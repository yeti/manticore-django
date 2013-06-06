manticore-django
================

Utility functionality for a Manticore Django project

Deployment script
-----------------
Manticore-django comes with a `fabric` deployment script. The script is based on Mezzanine's deployment script with additional features.
These features allow the script to deploy an *application* and *database* server using different `settings.py`.

Out of the box features:

* Multiple independent application servers
* Multiple independent cron servers (cron servers are identical to application servers with cron processes enabled)
* Master and slave Postgres server with Streaming Replication
* RabbitMQ asynchronous background task queue
* SSH key installation

### Requirements

These requirements should be listed in your `pip` requirements file:

* Django 1.5 or higher
* Mezzanine 1.4.3 or higher
* Celery (optional)

### Fabric Configuration

This Fabric deploy script in Manticore-Django is a drop-in replacement for Mezzanine's fabric deployment.
In addition to Mezzanine's script, you are able to configure application, cron, and database hosts separately.

In your `settings.py` file:

        FABRIC = {
             "SSH_USER": "", # SSH username
             "SSH_PASS":  "", # SSH password (consider key-based authentication)
             "SSH_KEY_PATH":  "", # Local path to SSH key file, for key-based auth
             "DEPLOY_SSH_KEY_PATH": "", # Local path to an SSH private key that should be installed on the server for accessing remote repositories (optional)
             "DEPLOY_MY_PUBLIC_KEY": "~/.ssh/id_rsa.pub", # Local path to your SSH public key so you can access the server (optional)
             "DEPLOY_DB_CLUSTER_SSH_KEY_PATH":"", # Local path to an SSH private key that will be installed on DATABASE_HOSTS to install with the postgres user
             "APPLICATION_HOSTS": [], # List of hosts to deploy to, public IP addresses
             "DATABASE_HOSTS": [], # List of hosts to deploy to, public IP addresses for SSH access. First entry is master, others are slaves.
             "CRON_HOSTS": [], # Optional list of hosts to run the cron job, public IP addresses, defaults to APPLICATION_HOSTS if not specified
             "PRIVATE_APPLICATION_HOSTS": [], # List of private IP addresses which APPLICATION_HOSTS and CRON_HOSTS communicate with the database, defaults to 127.0.0.1
             "PRIVATE_DATABASE_HOSTS": [], # List of private IP addresses that DATABASE_HOSTS receives connections from the application server, defaults to 127.0.0.1. First entry is master, others are slaves.
             "PRIVATE_CRON_HOSTS": [], # Optional list of private IP addresses for CRON_HOSTS to communicate with the database, default is the same as PRIVATE_APPLICATION_HOSTS
             "VIRTUALENV_HOME":  "", # Absolute remote path for virtualenvs
             "PROJECT_NAME": "", # Unique identifier for project
             "REQUIREMENTS_PATH": "", # Path to pip requirements, relative to project
             "APT_REQUIREMENTS": ["",""], # Optional list of Debian apt-get packages that are prerequisities for pip packages
             "GUNICORN_PORT": 8000, # Port gunicorn will listen on
             "LOCALE": "en_US.UTF-8", # Should end with ".UTF-8"
             "LIVE_HOSTNAME": "www.example.com", # Host for public site.
             "SITENAME": "Default", # Registered sitename in Django.
             "REPO_URL": "", # Git or Mercurial remote repo URL for the project
             "DB_PASS": "", # Live database password
             "ADMIN_PASS": "", # Live admin user password
             "LINUX_DISTRO": "squeeze", # Linux distribution such as Debian 6.0 (squeeze), 7.0 (wheezy), Ubuntu 10.04 (lucid), Ubuntu 12.04 (precise)
         }

### deploy/live_settings.py

Add/replace the following lines to Mezzanine's `deploy/live_settings.py`:

        DATABASES = {
            "default": {
                # Ends with "postgresql_psycopg2", "mysql", "sqlite3" or "oracle".
                "ENGINE": "django.db.backends.postgresql_psycopg2",
                # DB name or path to database file if using sqlite3.
                "NAME": "%(proj_name)s",
                # Not used with sqlite3.
                "USER": "%(proj_name)s",
                # Not used with sqlite3.
                "PASSWORD": "%(db_pass)s",
                # Set to empty string for localhost. Not used with sqlite3.
                "HOST": "%(primary_database_host)s",
                # Set to empty string for default. Not used with sqlite3.
                "PORT": "",
            }
        }

        # Django filtering
        ALLOWED_HOSTS = [%(allowed_hosts)s]

        # Celery configuration
        BROKER_URL = 'amqp://%(proj_name)s:%(admin_pass)s@127.0.0.1:5672/%(proj_name)s'

        # ...

### deploy/celeryd.conf

Add this file to your deploy directory along with `crontab`, `gunicorn.conf.py`, `live_settings.py`, `nginx.conf`, and
`supervisorconf`.

        ; ==============================================
        ;  celery worker supervisor example for Django
        ; ==============================================

        [program:celery_%(proj_name)s]
        command=%(manage)s celery worker --loglevel=INFO
        directory=%(proj_path)s
        environment=PYTHONPATH='%(proj_path)s'
        user=nobody
        numprocs=1
        stdout_logfile=/var/log/%(proj_name)s.celeryd.log
        stderr_logfile=/var/log/%(proj_name)s.celeryd.log
        autostart=true
        autorestart=true
        startsecs=10

        ; Need to wait for currently executing tasks to finish at shutdown.
        ; Increase this if you have very long running tasks.
        stopwaitsecs = 600

        ; if rabbitmq is supervised, set its priority higher
        ; so it starts first
        priority=998


### Tested Environments

I tested the script with the following configurations:

* Debian 6 and Postgresql 9.2
* Debian 6 and Postgresql 8.4 (deprecated)

### Known Issues

* Each project must have its own database servers. Archiving, restoring, and Streaming Replication are tightly coupled
  to the database server.

* If the script fails in `fab all` because your project database already exists (i.e., an upgrade), you can
  complete the upgrade with `fab create:True deploy`.

*  Automatic failover is not implemented. If the master database fails, manually configure a slave database as the master.

* If a host is removed from APPLICATION_HOSTS, CRON_HOSTS, or DATABASE_HOSTS, you have to manually remove that
  host entry from the Postgresql database configuration files.

