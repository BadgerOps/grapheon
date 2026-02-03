"""
RouteHop model for storing traceroute data.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class RouteHop(Base):
    """
    Represents a single hop in a traceroute path.

    Tracks hop number, IP address, RTT values, and destination.
    """

    __tablename__ = "route_hops"

    id = Column(Integer, primary_key=True, index=True)

    # Trace identification
    trace_id = Column(String(64), nullable=False, index=True)  # Groups hops in same trace

    # Hop details
    hop_number = Column(Integer, nullable=False)
    hop_ip = Column(String(45))  # Can be null for * (timeout)
    hostname = Column(String(255))

    # RTT measurements (milliseconds)
    rtt_ms_1 = Column(Float)
    rtt_ms_2 = Column(Float)
    rtt_ms_3 = Column(Float)

    # Source and destination
    source_host = Column(String(255))  # Machine that ran traceroute
    dest_ip = Column(String(45), nullable=False)

    # Optional link to hosts table
    host_id = Column(Integer, ForeignKey("hosts.id", ondelete="SET NULL"), nullable=True)
    host = relationship("Host", backref="route_hops")

    # Metadata
    captured_at = Column(DateTime, default=datetime.utcnow)
    source_type = Column(String(50), default="traceroute")

    def __repr__(self):
        return f"<RouteHop(trace_id={self.trace_id}, hop={self.hop_number}, ip={self.hop_ip})>"
