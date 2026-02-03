# Graphēon - Frontend

React frontend for the Graphēon web application. Built with React, React Router, Vite, and Tailwind CSS.

## Project Structure

```
frontend/
├── public/                 # Static assets
├── src/
│   ├── api/
│   │   └── client.js      # API client with fetch wrapper
│   ├── components/
│   │   ├── HostTable.jsx  # Reusable host table component
│   │   ├── ImportForm.jsx # Paste data import form
│   │   └── FileUpload.jsx # File upload component
│   ├── pages/
│   │   ├── Dashboard.jsx  # Main dashboard page
│   │   ├── Hosts.jsx      # Hosts list page
│   │   └── Import.jsx     # Import data page
│   ├── App.jsx            # Main app with routes
│   ├── main.jsx           # React entry point
│   └── index.css          # Tailwind imports
├── index.html             # HTML entry point
├── package.json           # Dependencies
├── vite.config.js         # Vite configuration
├── tailwind.config.js     # Tailwind CSS configuration
└── postcss.config.js      # PostCSS configuration
```

## Setup and Installation

### Prerequisites

- Use the Nix dev shell to standardize Node and Python versions.

### Install Dependencies

```bash
nix develop -c bash -lc "cd frontend && npm install"
```

### Development Server

Start the development server with Vite:

```bash
nix develop -c bash -lc "cd frontend && npm run dev"
```

The app will be available at `http://localhost:5173` by default.

Note: The development server proxies `/api` requests to `http://localhost:8000` (the backend API).

### Build for Production

```bash
nix develop -c bash -lc "cd frontend && npm run build"
```

This creates an optimized build in the `dist/` directory.

### Preview Production Build

```bash
nix develop -c bash -lc "cd frontend && npm run preview"
```

## Features

### Dashboard (`/`)
- Displays total number of hosts
- Shows recent import history
- Quick navigation to other pages
- System status indicator

### Hosts Page (`/hosts`)
- Table view of all network hosts
- Columns: IP Address, Hostname, OS Family, Device Type, Last Seen
- Click row to view host details
- Soft delete functionality with confirmation

### Import Page (`/import`)
- Two import methods:
  - **Paste Data**: Textarea for pasting raw data
  - **Upload File**: File upload for importing data files
- Both methods require:
  - Source Type: (nmap, netstat, arp, traceroute, ping)
  - Source Host: IP or hostname of the source

## API Client (`src/api/client.js`)

Simple fetch wrapper for backend API calls:

### Host Functions
- `getHosts()` - Fetch all hosts
- `getHost(id)` - Fetch specific host
- `createHost(data)` - Create new host
- `updateHost(id, data)` - Update host
- `deleteHost(id)` - Delete host

### Import Functions
- `importRaw(sourceType, sourceHost, rawData)` - Import raw text data
- `importFile(file, sourceType, sourceHost)` - Import file data
- `getImports()` - Fetch import history

## Styling

The application uses Tailwind CSS for styling. Utility classes are applied directly to elements.

Key styling features:
- Responsive design with mobile-first approach
- Dark navigation bar with white text
- Card-based layout for content
- Forms with focus states
- Hover effects on interactive elements
- Color scheme: blues and grays with accent colors

## Configuration Files

### vite.config.js
- Configures React plugin for JSX support
- Sets up API proxy to localhost:8000

### tailwind.config.js
- Configures content paths for Tailwind
- Extends default theme (currently uses defaults)

### postcss.config.js
- Integrates Tailwind CSS and Autoprefixer

## Technologies Used

- **React 18.2**: UI library
- **React Router 6.20**: Client-side routing
- **Vite 5.0**: Build tool and dev server
- **Tailwind CSS 3.3**: Utility-first CSS framework
- **PostCSS 8.4**: CSS transformation
- **Autoprefixer 10.4**: Browser prefix automation

## Browser Support

Works with all modern browsers that support ES modules and CSS Grid/Flexbox.

## Development Notes

- Components use React hooks (useState, useEffect)
- API calls are made with the built-in Fetch API
- Error handling is implemented with try-catch blocks
- Success messages auto-dismiss after 3 seconds
- Deletion requires user confirmation
- Form validation is included in components

## Future Enhancements

Potential additions:
- Host detail view page
- Advanced filtering and search
- Export functionality
- Data visualization (charts, graphs)
- Authentication and authorization
- Real-time updates with WebSocket
- Pagination for large datasets
