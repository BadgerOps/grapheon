from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, Index
from database import Base


class VLANConfig(Base):
    """
    VLAN configuration for network visualization.

    Maps subnet CIDRs to VLAN IDs so hosts can be automatically grouped
    into VLANs based on their IP addresses. Used by the network map to
    build compound node hierarchy: VLAN → Subnet → Host.
    """

    __tablename__ = "vlan_configs"

    id = Column(Integer, primary_key=True, index=True)

    # VLAN identity
    vlan_id = Column(Integer, unique=True, nullable=False, index=True)  # 802.1Q VLAN ID
    vlan_name = Column(String(255), nullable=False)  # Human-readable name
    description = Column(Text, nullable=True)

    # Subnet mapping — list of CIDR strings that belong to this VLAN
    # e.g., ["192.168.10.0/24", "10.10.10.0/24"]
    subnet_cidrs = Column(JSON, nullable=True)

    # Visualization
    color = Column(String(7), nullable=True)  # Hex color for map display, e.g. "#3b82f6"

    # Management
    is_management = Column(Boolean, default=False)  # Management VLAN flag

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_vlan_config_vlan_id", "vlan_id"),
    )

    def __repr__(self):
        return f"<VLANConfig(vlan_id={self.vlan_id}, name={self.vlan_name})>"
