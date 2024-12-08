# T2 CI/CD Pipeline CLI Tool Documentation

A command-line interface tool for managing CI/CD pipelines with comprehensive database integration and reporting capabilities.

## Installation

```bash
# Install the package
pip install -e .

# Uninstall the package
pip uninstall t2-cicd
```

## Basic Commands

### Help and Configuration
```bash
# Show general help
t2-cicd --help

# Show help for specific command
t2-cicd help <command_name>

# Validate configuration
t2-cicd check --config-file pipelines.yml

# Perform a dry run
t2-cicd dry-run <config_file>
```

### Repository Operations
```bash
# Get repository path
t2-cicd get-repo --path <path>

# Read configuration from repository
t2-cicd read-config --repo <repo_path> --file-name <config_file> --override <key=value>
```

### Pipeline Execution
```bash
# Run pipeline
t2-cicd run [--local] --repo <repo_url> --branch <branch> --commit <hash> --pipeline <name> --file <config_file> --override <key=value>

# Check pipeline status
t2-cicd status --repo <repo_url> --pipeline <name> --days <number>
```

## Database Commands

### Repository Management
```bash
# Create repository
t2-cicd db repo create <repo_url> [--local]

# Get repository info
t2-cicd db repo get <repo_id>
```

### Pipeline Management
```bash
# Create pipeline
t2-cicd db pipeline create <repo_id> <pipeline_name>

# Get pipeline info
t2-cicd db pipeline get <pipeline_id>
```

### Pipeline Run Management
```bash
# Create pipeline run
t2-cicd db run create <status> <pipeline_id> <git_commit_hash> <run_number> \
    [--start-time <ISO_time>] [--end-time <ISO_time>]

# Get pipeline run info
t2-cicd db run get <pipeline_run_id>
```

### Stage Management
```bash
# Create stage
t2-cicd db stage create <pipeline_run_id> <status> <run_number> \
    [--start-time <ISO_time>] [--end-time <ISO_time>]

# Get stage info
t2-cicd db stage get <stage_id>
```

### Job Management
```bash
# Create job
t2-cicd db job create <stage_id> <status> <run_number> [--allow-failure] \
    [--start-time <ISO_time>] [--end-time <ISO_time>]

# Get job info
t2-cicd db job get <job_id>
```

## Report Commands

```bash
# List all pipeline runs for a repository
t2-cicd report list --repo <repo_url> [--local]

# List specific pipeline runs
t2-cicd report list --repo <repo_url> [--local] --pipeline <name>

# Get pipeline run summary
t2-cicd report summary <pipeline_name> <run_number>

# Get stage summary (using ID or name)
t2-cicd report stage <pipeline_name> <run_number> --id <stage_id>
t2-cicd report stage <pipeline_name> <run_number> --name <stage_name>
t2-cicd report stage <pipeline_name> <run_number> --id <stage_id> --name <stage_name>

# Get job summary (using stage ID or name)
t2-cicd report job <pipeline_name> <run_number> <job_id> --id <stage_id>
t2-cicd report job <pipeline_name> <run_number> <job_id> --name <stage_name>
t2-cicd report job <pipeline_name> <run_number> <job_id> --id <stage_id> --name <stage_name>
```

## API Endpoints

### Repository Endpoints
- `POST /repo/post/{repo_url}/{is_local}` - Create repository
- `GET /repo/get/{repo_id}` - Get repository information

### Pipeline Endpoints
- `POST /pipeline/post/{repo_id}/{pipeline_name}` - Create pipeline
- `GET /pipeline/get/{pipeline_id}` - Get pipeline information
- `GET /pipeline/{pipeline_name}/run/{run_number}/summary` - Get pipeline run summary

### Pipeline Run Endpoints
- `POST /pipeline_run/post/{status}/{pipeline_id}/{git_commit_hash}/{run_number}/{start_time}/{end_time}` - Create pipeline run
- `GET /pipeline_run/get/{pipeline_run_id}` - Get pipeline run information

### Stage Endpoints
- `POST /stage/post/{pipeline_run_id}/{status}/{run_number}/{start_time}/{end_time}` - Create stage
- `GET /stage/get/{stage_id}` - Get stage information
- `GET /pipeline/{pipeline_name}/run/{run_number}/stage/summary` - Get stage summary
  - Query Parameters:
    - `stage_id`: (Optional) Stage ID
    - `stage_name`: (Optional) Stage name

### Job Endpoints
- `POST /job/post/{stage_id}/{status}/{allow_failure}/{run_number}/{start_time}/{end_time}` - Create job
- `GET /job/get/{job_id}` - Get job information
- `GET /pipeline/{pipeline_name}/run/{run_number}/stage/job/{job_id}/summary` - Get job summary
  - Query Parameters:
    - `stage_id`: (Optional) Stage ID
    - `stage_name`: (Optional) Stage name

### Report Endpoints
- `GET /report` - Get comprehensive reports
  - Query Parameters:
    - `repo`: Repository URL or path
    - `local`: Boolean indicating if repository is local
    - `pipeline`: (Optional) Pipeline name filter
    - `run`: (Optional) Run number filter
    - `stage`: (Optional) Stage ID filter
    - `job`: (Optional) Job ID filter

## Status Codes
The following status codes are used throughout the system:
- `1`: Success
- `2`: Failed
- `3`: Pending
- Additional status codes may be defined in the database's Status table

## Important Notes

1. Time Formats
   - All timestamps must be provided in ISO format (YYYY-MM-DDTHH:MM:SS)
   - If not provided, current time will be used as default

2. Configuration
   - Configuration files can be in YAML format
   - Multiple configuration overrides can be specified using `--override` multiple times
   - Configuration values follow the format `key=value`

3. Local vs Remote
   - Use `--local` flag when working with local repositories
   - Remote repositories require full URL

4. Database Operations
   - All database operations are performed through the FastAPI server
   - Server must be running on http://127.0.0.1:8001
   - Use appropriate error handling for database operations

5. Stage Identification
   - Stages can be identified by either ID or name
   - When both ID and name are provided, they must match
   - At least one identifier (ID or name) must be provided

6. Performance
   - For large pipelines, consider using filters in report commands
   - Database queries are optimized for common operations
   - Status monitoring is available for up to 7 days by default