import argparse
import sys


def deploy_to_staging():
    print("Deploying application to the staging environment...")
    # Add your deployment logic here
    # Example: Print the environment for illustration
    print("Environment: Staging")
    # Placeholder for deployment steps:
    # - Transfer files
    # - Execute remote commands
    # - Notify success or failure
    print("Deployment to staging complete!")


def deploy_to_production():
    print("Deploying application to the production environment...")
    # Add your production deployment logic here
    print("Environment: Production")
    # Placeholder for production deployment steps
    print("Deployment to production complete!")


def main():
    parser = argparse.ArgumentParser(description="Deploy the application to a specified environment.")
    parser.add_argument('--env', type=str, required=True,
                        help="Specify the environment to deploy to (e.g., 'staging' or 'production').")
    args = parser.parse_args()

    if args.env.lower() == 'staging':
        deploy_to_staging()
    elif args.env.lower() == 'production':
        deploy_to_production()
    else:
        print(f"Error: Unknown environment '{args.env}'. Please specify 'staging' or 'production'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
