ENV_PATH="../.env"
COMPOSE_FILE_PATH="./docker-compose.yml"

echo "=== Starting database initialization script ==="

# Load environment variables properly
if [ -f "$ENV_PATH" ]; then
    echo "Loading environment variables from $ENV_PATH"
    # Read each line and export properly formatted variables
    while IFS='=' read -r key value; do
        # Skip empty lines and comments
        if [ -n "$key" ] && ! [[ "$key" =~ ^# ]]; then
            # Remove any trailing whitespace
            value=$(echo "$value" | tr -d '\r')
            # Export the variable
            export "$key"="$value"
        fi
    done < "$ENV_PATH"

    # Debug: Print loaded variables
    echo "Loaded environment variables:"
    echo "POSTGRES_USER=$POSTGRES_USER"
    echo "POSTGRES_DB=$POSTGRES_DB"
else
    echo "ERROR: .env file not found at $ENV_PATH"
    exit 1
fi

# Stop existing containers
echo "Cleaning up existing containers..."
docker-compose -f "$COMPOSE_FILE_PATH" down

# Start the PostgreSQL container
echo "Starting PostgreSQL container..."
docker-compose -f "$COMPOSE_FILE_PATH" up -d

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
ATTEMPTS=0
MAX_ATTEMPTS=30

until docker exec my_postgres pg_isready -U "$POSTGRES_USER" || [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; do
    ATTEMPTS=$((ATTEMPTS + 1))
    echo "Attempt $ATTEMPTS of $MAX_ATTEMPTS..."
    sleep 2
done

if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
    echo "ERROR: PostgreSQL failed to become ready"
    docker-compose -f "$COMPOSE_FILE_PATH" logs postgres
    exit 1
fi

echo "PostgreSQL is ready."

# Initialize schema if needed
echo "Checking database connection..."
if docker exec my_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt' 2>/dev/null; then
    echo "Successfully connected to database."

    if ! docker exec my_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt' | grep -q "status"; then
        echo "Initializing schema..."
        for f in ./migrations/*.sql; do
            if [ -f "$f" ]; then
                echo "Executing $f..."
                docker exec -i my_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$f"
            fi
        done
    else
        echo "Schema already exists."
    fi
else
    echo "Error connecting to database. Check credentials and database status."
    docker-compose -f "$COMPOSE_FILE_PATH" logs postgres
fi

# Final status check
echo "Final database status:"
docker exec my_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\dt'
docker exec my_postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\l+'