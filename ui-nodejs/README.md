# ECS App Tester UI

Simple Node.js web interface for controlling the ECS App Tester API.

## Setup

1. Install dependencies:
   ```bash
   make ui-install
   ```

2. Start the UI server:
   ```bash
   make ui-start
   ```

3. Open http://localhost:3000 in your browser

## Features

- **Bootstrap Workspace**: Create a new workspace with S3 bucket and app configurations
- **Start App**: Launch an app in a workspace
- **Stop App**: Stop a running app
- **Sync Files**: Sync app files from S3 to EFS

The UI forwards requests to the controller API running on port 8000. Make sure the controller is running first:

```bash
make api-run
```