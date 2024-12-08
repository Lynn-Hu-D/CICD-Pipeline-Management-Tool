# `t2-cicd` CLI Tool Documentation

## Overview
Welcome to the open-source `t2-cicd` CLI tool repository! This documentation is divided into two sections: one for **Client Users** and one for **Developers**. Whether you're using the tool or contributing to its development, this guide will provide all the necessary information to get started.

### About T2-CICD CLI Tool 

The `t2-cicd` CLI tool enables users to run a specific pipeline, cancel a running pipeline, and query logs for pipelines, stages, and jobs.
The t2-cicd CLI tool is designed to simplify pipeline management by providing robust command-line features. Users can:

- **Run pipelines**: Execute specific pipelines with ease.
- **Cancel pipelines**: Halt running pipelines as needed.
- **Query logs**: Retrieve detailed logs for pipelines, stages, and jobs for better debugging and monitoring.

For a detailed breakdown of the tool's features and their development status, refer to the [Feature Status Documentation](FeatureStatus.md). This document provides a transparent overview of completed features and work in progress.


## New Users
This section is intended for users who will interact with the `t2-cicd` CLI tool. It contains detailed instructions for installing, configuring, and using the tool effectively.


**[Client Instructions](dev-docs/Client/ClientInstruction.md):** This file provides step-by-step instructions on how to install, configure, and use the `t2-cicd` CLI tool. It includes explanations of the available commands, how to interact with the tool, and how to leverage its features.

---

## New Developers
This section is aimed at developers working on the `t2-cicd` CLI tool. It covers the system’s architecture, API documentation, database design, and a detailed breakdown of the tool’s components.

#### Table of Contents:
- [Prerequisites and QickStart](dev-docs/Developer/QuickStart.md)

    This section provides essential information and guidance to get started with the `t2-cicd` CLI tool. It covers:  
    - Steps to set up the t2-cicd CLI tool and required tools.
    - Overview of the project’s directory structure.
    - Instructions to run, validate, and test the project locally.

- [Project Proposal](dev-docs/Developer/Proposal.md)

    Document outlining the goals, motivation, and scope of the t2-cicd CLI tool project.

- [System Design](dev-docs/Developer/DesignDoc_1.0.md) 

    This document outlines the high-level architecture of the system, including:
    - Key components in the system
    - Communication flow between components
    - Key design decisions and trade-offs

- [Server Documentation](dev-docs/Developer/Server.md)
    
    Explains the server-side operations of the t2-cicd CLI tool, covering:
    - API endpoints and usage
    - Communication with other components
    - Database integration
    - Testing and debugging

- [Database Design](dev-docs/Developer/Updated-DB-Design.md)

    Details on the database schema for the tool:
    - Table structures, keys, and relationships
    - Sample queries for retrieving pipeline information

- [Deployment Instructions](dev-docs/Developer/DeployInstruction.md)

    Comprehensive steps to deploy the system using Docker.
   
---

## Contributing
If you're interested in contributing to the development of the `t2-cicd` CLI tool, please refer to the developer documentation for detailed information on the system design and components. For general usage instructions, see the client documentation.

To contribute, simply fork the repository, make your changes, and submit a pull request. If you encounter any issues or bugs, please open an issue in the repository, and the maintainers will be happy to assist you.

---
