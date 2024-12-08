-- Insert sample data into Repo table
INSERT INTO Repo (repo_url, is_local)
VALUES 
    ('https://github.com/example/repo1', TRUE),
    ('https://github.com/example/repo2', FALSE),
    ('https://github.com/example/repo3', TRUE);

-- Insert sample data into Pipeline table
INSERT INTO Pipeline (repo_id, pipeline_name)
VALUES 
    (1, 'Pipeline 1'),
    (2, 'Pipeline 2'),
    (3, 'Pipeline 3');

-- Insert sample data into Pipeline_run table
INSERT INTO Pipeline_run (status, pipeline_id, git_commit_hash, run_number, start_time, end_time)
VALUES 
    (1, 1, 'abcd1234', 1, '2024-01-01 10:00:00', '2024-01-01 10:30:00'),
    (2, 2, 'efgh5678', 2, '2024-01-02 12:00:00', '2024-01-02 12:45:00'),
    (3, 3, 'ijkl9101', 3, '2024-01-03 14:00:00', '2024-01-03 14:20:00');

-- Insert sample data into Stage table
INSERT INTO Stage (pipeline_run_id, status, run_number, start_time, end_time)
VALUES 
    (1, 1, 1, '2024-01-01 10:05:00', '2024-01-01 10:10:00'),
    (2, 2, 2, '2024-01-02 12:10:00', '2024-01-02 12:20:00'),
    (3, 3, 3, '2024-01-03 14:10:00', '2024-01-03 14:15:00');

-- Insert sample data into Job table
INSERT INTO Job (stage_id, status, allow_failure, run_number, start_time, end_time)
VALUES 
    (1, 1, FALSE, 1, '2024-01-01 10:05:30', '2024-01-01 10:06:00'),
    (2, 2, TRUE, 2, '2024-01-02 12:10:30', '2024-01-02 12:11:00'),
    (3, 3, FALSE, 3, '2024-01-03 14:10:30', '2024-01-03 14:11:00');
