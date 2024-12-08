-- File: migrations/init_schema.sql

-- Table: Status
CREATE TABLE IF NOT EXISTS Status (
    status_code SERIAL PRIMARY KEY,
    status_name VARCHAR(50) UNIQUE
);

-- Insert initial data into Status table
INSERT INTO Status (status_name)
    SELECT 'pending' WHERE NOT EXISTS (SELECT 1 FROM Status WHERE status_name = 'pending');
INSERT INTO Status (status_name)
    SELECT 'running' WHERE NOT EXISTS (SELECT 1 FROM Status WHERE status_name = 'running');
INSERT INTO Status (status_name)
    SELECT 'completed' WHERE NOT EXISTS (SELECT 1 FROM Status WHERE status_name = 'completed');
INSERT INTO Status (status_name)
    SELECT 'failed' WHERE NOT EXISTS (SELECT 1 FROM Status WHERE status_name = 'failed');
INSERT INTO Status (status_name)
    SELECT 'canceled' WHERE NOT EXISTS (SELECT 1 FROM Status WHERE status_name = 'canceled');

-- Table: Repo
CREATE TABLE IF NOT EXISTS Repo (
    repo_id SERIAL PRIMARY KEY,
    repo_url VARCHAR(255),
    is_local BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: Pipeline
CREATE TABLE IF NOT EXISTS Pipeline (
    pipeline_id SERIAL PRIMARY KEY,
    repo_id INT REFERENCES Repo (repo_id),
    pipeline_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: Pipeline_run
CREATE TABLE IF NOT EXISTS Pipeline_run (
    pipeline_run_id SERIAL PRIMARY KEY,
    status INT REFERENCES Status (status_code),
    pipeline_id INT REFERENCES Pipeline (pipeline_id),
    git_commit_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    run_number INT,
    start_time TIMESTAMP,
    end_time TIMESTAMP
);

-- Table: Stage
CREATE TABLE IF NOT EXISTS Stage (
    stage_id SERIAL PRIMARY KEY,
    pipeline_run_id INT REFERENCES Pipeline_run (pipeline_run_id),
    stage_name VARCHAR(255),
    status INT REFERENCES Status (status_code),
    run_number INT,
    start_time TIMESTAMP,
    end_time TIMESTAMP
);

-- Table: Job
CREATE TABLE IF NOT EXISTS Job (
    job_id SERIAL PRIMARY KEY,
    stage_id INT REFERENCES Stage (stage_id),
    status INT REFERENCES Status (status_code),
    allow_failure BOOLEAN,
    run_number INT,
    start_time TIMESTAMP,
    end_time TIMESTAMP
);
