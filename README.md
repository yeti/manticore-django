manticore-django
================

Utility functionality for a Manticore Django project

Deployment script
-----------------
Manticore-django comes with a `fabric` deployment script. The script is based on Mezzanine's deployment script with additional features. These features allow the script to deploy an *application* and *database* server using different `settings.py`.

### Fabric Configuration

Fabric configuration is set in your `settings.py` file:

        FABRIC = 
             "SSH_USER": "", # SSH username
             "SSH_PASS":  "", # SSH password (consider key-based authentication)
             "SSH_KEY_PATH":  "", # Local path to SSH key file, for key-based auth
             "APPLICATION_HOSTS": [], # List of hosts to deploy to, public IP addresses
             "DATABASE_HOSTS": [], # List of hosts to deploy to, public IP addresses for SSH access
             "CRON_HOSTS": [], # Optional list of hosts to run the cron job, public IP addresses, defaults to APPLICATION_HOSTS if not specified
             "PRIVATE_APPLICATION_HOSTS": [], # List of private IP addresses which the application server uses to communicate with the database
             "PRIVATE_DATABASE_HOSTS": [], # List of private IP addresses that the database receives connections from the application server
             "VIRTUALENV_HOME":  "", # Absolute remote path for virtualenvs
             "PROJECT_NAME": "", # Unique identifier for project
             "REQUIREMENTS_PATH": "", # Path to pip requirements, relative to project
             "GUNICORN_PORT": 8000, # Port gunicorn will listen on
             "LOCALE": "en_US.UTF-8", # Should end with ".UTF-8"
             "LIVE_HOSTNAME": "www.example.com", # Host for public site.
             "REPO_URL": "", # Git or Mercurial remote repo URL for the project
             "DB_PASS": "", # Live database password
             "ADMIN_PASS": "", # Live admin user password
             "LINUX_DISTRO": "squeeze", # Linux distribution such as Debian 6.0 (squeeze), 7.0 (wheezy), Ubuntu 10.04 (lucid), Ubuntu 12.04 (precise)
         }

You are able to configure application and database hosts separately.

Tested environments:
* Debian 6 and Postgresql 9.2


