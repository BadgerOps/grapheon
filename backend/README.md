# Graphēon Backend

A FastAPI-based backend for aggregating and managing network data from various sources.

## Project Structure

```
backend/
├── config.py                 # Configuration settings
├── database.py              # SQLAlchemy async setup
├── main.py                  # FastAPI application entry point
├── schemas.py               # Pydantic request/response schemas
├── models/
│   ├── __init__.py
│   ├── host.py             # Host model
│   ├── port.py             # Port model
│   ├── connection.py       # Connection model (netstat)
│   ├── arp_entry.py        # ARP entry model
│   └── raw_import.py       # Raw import audit log
├── routers/
│   ├── __init__.py
│   ├── hosts.py            # Host CRUD endpoints
│   └── imports.py          # Import endpoints
├── parsers/                # Data parsers (for future implementation)
└── requirements.txt        # Python dependencies
```

## Installation

The backend standardizes on Python 3.12. Use the Nix dev shell for all Python commands.

```bash
nix develop
```

If you are not using Nix, create a Python 3.12 virtual environment and install dependencies from `requirements.txt` and `requirements-dev.txt`.

## Configuration

The application uses Pydantic settings. Create a `.env` file in the backend directory. Do not commit it.

```
DATABASE_URL=sqlite:///./data/network.db
CORS_ORIGINS=["http://localhost:5173"]
DEBUG=False
```

## Running the Application

```bash
nix develop -c bash -lc "python main.py"
```

Or with uvicorn directly:

```bash
nix develop -c bash -lc "uvicorn main:app --reload --host 0.0.0.0 --port 8000"
```

The API will be available at `http://localhost:8000`
- Interactive API docs: `http://localhost:8000/docs`
- Alternative API docs: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health`

## API Endpoints

### Health & Root
- `GET /health` - Health check
- `GET /api` - API root info

### Hosts
- `GET /api/hosts` - List all hosts (paginated)
- `GET /api/hosts/{id}` - Get single host with ports
- `POST /api/hosts` - Create new host
- `PUT /api/hosts/{id}` - Update host
- `DELETE /api/hosts/{id}` - Soft delete host

### Imports
- `POST /api/import/raw` - Import raw text data
- `POST /api/import/file` - Import file data
- `GET /api/imports` - List import history
- `GET /api/imports/{id}` - Get import details

### Correlation
- `POST /api/correlate` - Trigger host correlation

### Network
- `GET /api/network` - Graph data for network visualization

### Connections
- `GET /api/connections` - List parsed connection records

### ARP
- `GET /api/arp` - List ARP entries

### Search
- `GET /api/search` - Search hosts, ports, connections, and imports

### Export
- `GET /api/export` - Export data from the system

### Maintenance
- `POST /api/maintenance/cleanup` - Cleanup tasks and data maintenance

## Database Models

### Host
- IP addresses (IPv4 and IPv6)
- MAC address
- Hostname, FQDN, NetBIOS name
- OS information (name, version, family, confidence)
- Device type and vendor
- Criticality, owner, location
- Tags, notes, verification status
- First seen, last seen timestamps
- Source types (tracking data origin)

### Port
- Port number and protocol (TCP/UDP)
- Service information (name, version, extra info)
- CPE and product details
- State and confidence levels
- Associated with a Host

### Connection
- Local and remote IP addresses and ports
- Protocol and state
- Process information (PID, name)
- Tracks network connections (netstat data)

### ARPEntry
- IP to MAC address mappings
- Interface information
- Resolution status

### RawImport
- Audit log for imported data
- Stores raw text data
- Parse status and results
- Source type and filename
- Associated tags and notes

## Development Notes

- All database operations are async using SQLAlchemy with aiosqlite
- Models use proper indexing for performance
- Soft deletes are used for hosts (set is_active=False)
- Pagination is included for list endpoints
- CORS is configured for the frontend (localhost:5173)
- Database is automatically initialized on application startup
