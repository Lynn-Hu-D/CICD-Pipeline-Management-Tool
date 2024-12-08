from collections import deque


def handle_dependency(config):
    output = []
    for file_dict in config:
        for file_path, data in file_dict.items():
            jobs = data.get('jobs', {})
            pipeline_name = data.get('name', 'Unnamed Pipeline')  # Extract pipeline name
            global_vars = data.get('global', {})  # Extract global variables
            stages = data.get('stages', [])
            # Build the stage order list
            stage_order = [stage['name'] for stage in stages]
            # Build mapping from stage name to job names
            stage_to_jobs = {}
            job_to_stage = {}
            for job_name, job_data in jobs.items():
                stage_name = job_data.get('stage')
                if stage_name not in stage_order:
                    print(f"Error: Job '{job_name}' references undefined stage '{stage_name}'")
                    continue
                stage_to_jobs.setdefault(stage_name, []).append(job_name)
                job_to_stage[job_name] = stage_name
            # Build the dependency chains
            dependency_chains = []
            for stage_name in stage_order:
                stage_jobs = stage_to_jobs.get(stage_name, [])
                if not stage_jobs:
                    continue
                # Build dependency graph for jobs in this stage
                dependency_graph = {}
                for job_name in stage_jobs:
                    job_data = jobs[job_name]
                    needs = job_data.get('needs', [])
                    # Filter needs to only include jobs in the same stage
                    filtered_needs = [n for n in needs if job_to_stage.get(n) == stage_name]
                    dependency_graph[job_name] = filtered_needs
                # Assign levels to jobs in this stage
                job_levels = assign_levels(dependency_graph)
                # Group jobs by level
                levels = {}
                for job_name, level in job_levels.items():
                    job_data = jobs[job_name]
                    levels.setdefault(level, []).append({job_name: job_data})
                # Build the list of levels
                stage_dependency_chain = [levels[level] for level in sorted(levels)]
                # Add to dependency chains
                dependency_chains.append({'stage': stage_name, 'jobs': stage_dependency_chain})
            output.append({file_path: {'dependency': dependency_chains,
                                       'pipeline_name': pipeline_name,
                                       'stages': stages,
                                       'global_vars': global_vars}
                           })
    return output


def assign_levels(dependency_graph):
    # Kahn's algorithm for topological sorting and level assignment
    # Initialize in-degree counts
    in_degree = {job: 0 for job in dependency_graph}
    for job, deps in dependency_graph.items():
        for dep in deps:
            in_degree[dep] = in_degree.get(dep, 0) + 1
    # Queue for jobs with in-degree zero
    queue = deque([job for job, degree in in_degree.items() if degree == 0])
    job_levels = {}
    while queue:
        current_job = queue.popleft()
        current_level = job_levels.get(current_job, 0)
        for dependent_job in dependency_graph:
            if current_job in dependency_graph[dependent_job]:
                in_degree[dependent_job] -= 1
                if in_degree[dependent_job] == 0:
                    job_levels[dependent_job] = current_level + 1
                    queue.append(dependent_job)
    # Assign level 0 to any jobs not yet assigned a level
    for job in dependency_graph:
        if job not in job_levels:
            job_levels[job] = 0
    return job_levels
