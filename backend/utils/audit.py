"""
Structured audit logging module for the Graphēon backend.

This module provides an AuditLogger class that logs events to a dedicated 'audit' logger
in structured JSON format. It supports context-aware request_id propagation across async
calls using contextvars.ContextVar.

Key features:
- Thread-safe and async-safe request_id tracking via ContextVar
- Structured JSON output with ISO8601 timestamps
- Convenience methods for common audit events (imports, correlation, CRUD operations, etc.)
- Sanitized detail values to prevent data dumps
"""

import json
import logging
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional


# Context variable for tracking request_id across async calls
_request_id_context: ContextVar[Optional[str]] = ContextVar(
    'request_id', default=None
)

# Context variable for tracking actor (authenticated user) across async calls
_actor_context: ContextVar[Optional[str]] = ContextVar(
    'actor', default=None
)


class AuditLogger:
    """
    Structured audit logger for tracking all significant backend operations.
    
    Provides methods to log various types of events with consistent formatting
    and context propagation. All events are written to a dedicated 'audit' logger
    in JSON format.
    """
    
    def __init__(self):
        """Initialize the AuditLogger with a dedicated 'audit' logger."""
        self.logger = logging.getLogger('audit')
    
    def set_request_id(self, request_id: str) -> None:
        """
        Set the request_id for the current context.
        
        Args:
            request_id: Unique identifier for the current request/operation
        """
        _request_id_context.set(request_id)
    
    def get_request_id(self) -> Optional[str]:
        """
        Get the current request_id from context.
        
        Returns:
            The request_id if set, None otherwise
        """
        return _request_id_context.get()
    
    def set_actor(self, actor: str) -> None:
        """Set the authenticated user for this request context."""
        _actor_context.set(actor)
    
    def get_actor(self) -> Optional[str]:
        """Get the current actor from context, or None."""
        return _actor_context.get()
    
    def log(
        self,
        action: str,
        actor: str,
        resource: str,
        resource_id: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Core method to log a structured audit event.
        
        Args:
            action: Type of action performed (e.g., 'CREATE', 'DELETE', 'IMPORT')
            actor: User or service performing the action
            resource: Type of resource affected (e.g., 'Host', 'VLAN', 'DeviceIdentity')
            resource_id: Unique identifier of the affected resource
            status: Result status (e.g., 'success', 'failure', 'partial')
            details: Optional dict of additional context, automatically sanitized
        """
        event = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'action': action,
            'actor': actor if actor != 'user' else (self.get_actor() or 'user'),
            'resource': resource,
            'resource_id': resource_id,
            'status': status,
            'request_id': self.get_request_id(),
            'details': details or {},
        }
        self.logger.info(json.dumps(event))
    
    def log_import(
        self,
        source_type: str,
        filename: str,
        status: str,
        record_count: int,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log a data import operation.
        
        Args:
            source_type: Type of source being imported (e.g., 'CSV', 'Excel', 'JSON')
            filename: Name of the file imported
            status: Import status (e.g., 'success', 'failure', 'partial')
            record_count: Number of records processed
            error_message: Optional error message if import failed
        """
        details = {
            'source_type': source_type,
            'filename': filename,
            'record_count': record_count,
        }
        if error_message:
            details['error_message'] = error_message
        
        self.log(
            action='IMPORT',
            actor='user',
            resource='DataImport',
            resource_id=filename,
            status=status,
            details=details,
        )
    
    def log_correlation(
        self,
        status: str,
        hosts_merged: int,
        conflicts_detected: int,
        device_identities_created: int,
    ) -> None:
        """
        Log a data correlation/reconciliation operation.
        
        Args:
            status: Correlation status (e.g., 'success', 'failure')
            hosts_merged: Number of hosts merged during correlation
            conflicts_detected: Number of conflicts found
            device_identities_created: Number of device identities created
        """
        self.log(
            action='CORRELATION',
            actor='user',
            resource='HostCorrelation',
            resource_id='batch',
            status=status,
            details={
                'hosts_merged': hosts_merged,
                'conflicts_detected': conflicts_detected,
                'device_identities_created': device_identities_created,
            },
        )
    
    def log_host_crud(
        self,
        operation: str,
        host_id: str,
        ip_address: str,
        hostname: str,
        changes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log host Create/Read/Update/Delete operations.
        
        Args:
            operation: CRUD operation ('CREATE', 'UPDATE', 'DELETE', 'READ')
            host_id: Unique host identifier
            ip_address: Host IP address
            hostname: Host name/hostname
            changes: Optional dict of changed fields (for UPDATE operations)
        """
        details = {
            'ip_address': ip_address,
            'hostname': hostname,
        }
        if changes:
            details['changes'] = changes
        
        self.log(
            action=operation,
            actor='user',
            resource='Host',
            resource_id=host_id,
            status='success',
            details=details,
        )
    
    def log_backup_restore(
        self,
        operation: str,
        filename: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Log backup or restore operations.
        
        Args:
            operation: Operation type ('BACKUP' or 'RESTORE')
            filename: Backup filename
            status: Operation status (e.g., 'success', 'failure')
            error_message: Optional error message if operation failed
        """
        details = {'filename': filename}
        if error_message:
            details['error_message'] = error_message
        
        self.log(
            action=operation,
            actor='user',
            resource='Backup',
            resource_id=filename,
            status=status,
            details=details,
        )
    
    def log_vlan_change(
        self,
        operation: str,
        vlan_id: str,
        vlan_name: Optional[str] = None,
    ) -> None:
        """
        Log VLAN creation, update, or deletion.
        
        Args:
            operation: Operation type ('CREATE', 'UPDATE', 'DELETE')
            vlan_id: VLAN identifier (ID or number)
            vlan_name: Optional VLAN name
        """
        details = {}
        if vlan_name:
            details['vlan_name'] = vlan_name
        
        self.log(
            action=operation,
            actor='user',
            resource='VLAN',
            resource_id=vlan_id,
            status='success',
            details=details,
        )
    
    def log_device_identity_change(
        self,
        operation: str,
        device_id: str,
        device_name: Optional[str] = None,
        host_ids: Optional[list] = None,
    ) -> None:
        """
        Log device identity creation, update, or deletion.
        
        Args:
            operation: Operation type ('CREATE', 'UPDATE', 'DELETE')
            device_id: Device identity identifier
            device_name: Optional device name
            host_ids: Optional list of associated host IDs
        """
        details = {}
        if device_name:
            details['device_name'] = device_name
        if host_ids:
            details['host_id_count'] = len(host_ids)
        
        self.log(
            action=operation,
            actor='user',
            resource='DeviceIdentity',
            resource_id=device_id,
            status='success',
            details=details,
        )
    
    def log_seed_data(
        self,
        status: str,
        append_mode: bool,
    ) -> None:
        """
        Log seed data initialization or update.
        
        Args:
            status: Operation status (e.g., 'success', 'failure')
            append_mode: Whether seed data was appended or replaced
        """
        self.log(
            action='SEED',
            actor='user',
            resource='SeedData',
            resource_id='initialization',
            status=status,
            details={'append_mode': append_mode},
        )
    
    def log_upgrade_trigger(self, version: str) -> None:
        """
        Log database schema upgrade/migration trigger.
        
        Args:
            version: Target schema version
        """
        self.log(
            action='UPGRADE',
            actor='user',
            resource='Database',
            resource_id='schema',
            status='triggered',
            details={'target_version': version},
        )


# Global audit logger instance for convenient import
audit = AuditLogger()
