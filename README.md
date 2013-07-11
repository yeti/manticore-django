manticore-django
================

Utility functionality for a Manticore Django project

Fabric Script
=============

Fabric script
--------------
Manticore-django comes with a `fabric` script for creating, cloning, and deploying Python Django source code. The script is inspired by Mezzanine's deployment script with additional features. These features allow the script to deploy an *application* and *database* server.

Setup for:

* Three-tier topology
  * Single application/cron/database server
  * Multiple independent application servers
  * Multiple independent cron servers (cron servers are identical to application servers with cron processes enabled)
  * Master and slave Postgres server with Streaming Replication

* Multiple target deployment
  * Supports targets for *development* (default), *staging*, and *production*

* Vagrant+Pycharm support
  * Creating and cloning local projects
  * Identical Vagrant tech stack as live servers
  * Does not mess up your local computer's tech stack

### Tech Stack

Out of the box tech stack:

* RabbitMQ asynchronous background task queue
* Celery connection between RabbitMQ and Python Django
* SSH public key deployment to live servers
* Your source code repository's private key installation on live servers
* Database public/private keys installation on database servers

### Requirements

Prerequisities for running the script:

* Python 2.6 or higher
* `fabric`
* `simplejson`

These requirements should be listed in your `requirements/requirements.txt` file:

* Django 1.5 or higher
* Mezzanine 1.4.3 or higher
* django-celery (optional)

### Setup

1. A valid installation of Python 2.6 or higher must be installed on your computer.

2. Fabric must be installed: `pip install fabric`

3. Create `fabric_settings.py` in the same directory as manage.py. See next section for details.

4. If this is a first time installation, the project has to be setup:
  a. remove Mezzanine's fabric script;
  b. rename copies of `deploy/live_settings.py` as:
    * `deploy/development_settings.py`, 
    * `deploy/production_settings.py`, 
    * `deploy/staging_settings.py`
  d. add `deploy/celeryd.conf`. See the next section for details.

Your directory structure should look like:

* deploy
  * crontab
  * gunicorn.conf.py
  * nginx.conf
  * **celeryd.conf**
  * **development_settings.py**
  * **production_settings.py**
  * **staging_settings.py**
  * supervisor.conf
* manage.py
* local_settings.py
* **fabric_settings.py**
* settings.py
* urls.py
* ...

5. If you make major configuration changes, you should run `fab deploy.create:True deploy.deploy`.

6. If you are changing only source code, you should run `fab deploy.deploy` or `fab deploy.deployapp`

### Usage

After the script is configured properly (see next section), then you can run fabric tasks to setup and redeploy your app.

Before running any of these commands, you'll have to setup your server with a Debian-based operating system and have username+password SSH access.

Here's the command to setup your server the first time:

    fab -f path/to/fabfile deploy.all

Subsequently, you can reploy using:

    fab -f path/to/fabfile deploy.deploy

### Switching Targets

1. `fab deploy.development ...`
2. `fab deploy.staging ...`
3. `fab deploy.production ...`

The **development** environment (1) is default.

If something isn't working right and you want to know why, pass in a parameter `True` to these commands.

1. `fab deploy.development:True`
2. `fab deploy.staging:True`
3. `fab deploy.production:True`


Script Configuration
--------------------

### `fabric_settings.py`

In your `fabric_settings.py` file:

        FABRIC = {
            "development": {
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
                 "REQUIREMENTS_PATH": "requirements/requirements.txt", # Path to pip requirements, relative to project
                 "APT_REQUIREMENTS": ["",""], # Optional list of Debian apt-get packages that are prerequisities for pip packages
                 "GUNICORN_PORT": 8000, # Port gunicorn will listen on
                 "LOCALE": "en_US.UTF-8", # Should end with ".UTF-8"
                 "LIVE_HOSTNAME": "www.example.com", # Host for public site.
                 "SITENAME": "Default", # Registered sitename in Django.
                 "REPO_URL": "", # Git or Mercurial remote repo URL for the project
                 "DB_PASS": "", # Live database password
                 "ADMIN_PASS": "", # Live admin user password
                 "LINUX_DISTRO": "squeeze", # Linux distribution such as Debian 6.0 (squeeze), 7.0 (wheezy), Ubuntu 10.04 (lucid), Ubuntu 12.04 (precise)
            },
            "staging": {
                 ...
            },
            "production" : {
                ...
            }
        }


### `deploy/development_settings.py`, `deploy/staging_settings.py`, and `deploy/production_settings.py`

Create server-specific settings for each of the specified targets:
* `deploy/development_settings.py`, 
* `deploy/staging_settings.py`, and 
* `deploy/production_settings.py`:

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

        # Mezzanine settings
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTOCOL", "https")

        CACHE_MIDDLEWARE_SECONDS = 60

        CACHE_MIDDLEWARE_KEY_PREFIX = "%(proj_name)s"

        CACHES = {
            "default": {
                "BACKEND": "django.core.cache.backends.memcached.MemcachedCache",
                "LOCATION": "127.0.0.1:11211",
            }
        }

        SESSION_ENGINE = "django.contrib.sessions.backends.cache"

        # Django 1.5+ requires a set of allowed hosts
        ALLOWED_HOSTS = [%(allowed_hosts)s]

        # Celery configuration (if django-celery is installed in requirements/requirements.txt)
        BROKER_URL = 'amqp://%(proj_name)s:%(admin_pass)s@127.0.0.1:5672/%(proj_name)s'

        # ...

### deploy/celeryd.conf

Add `deploy/celeryd.conf` to your project.

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


Creating and Cloning Projects with Vagrant
------------------------------------------

Usage scenario: you can use Pycharm to remotely connect to the Vagrant box for development. 

**TODO: we need to document this feature of the script**

### Setting up PyCharm

Prerequisites:

* VirtualBox
* Vagrant

### local_settings.py

If you are running the working (non-committed) version of Django from `/vagrant/`, then you'll have to configure `local_settings.py`:

        ...

        FABRIC = {
            "vagrant": {
                "SSH_USER": "vagrant", # SSH username
                "SSH_PASS":  "vagrant", # SSH password (consider key-based authentication)
                "SSH_KEY_PATH":  "", # Local path to SSH key file, for key-based auth

                # deployment SSH key
                #"DEPLOY_MY_PUBLIC_KEY": "~/.ssh/id_rsa.pub", # not needed because we are authenticating with username & password
                "DEPLOY_SSH_KEY_PATH": "", # local-file.pub
                #"DEPLOY_DB_CLUSTER_SSH_KEY_PATH": "", # local-file.pem, but not needed for Vagrant

                # Vagrant local box
                "APPLICATION_HOSTS": ['127.0.0.1:2222'], # SSH port for Vagrant is 2222
                "PRIVATE_APPLICATION_HOSTS": ['127.0.0.1'],
                "DATABASE_HOSTS": ['127.0.0.1:2222'],  # SSH port for Vagrant is 2222
                "PRIVATE_DATABASE_HOSTS":['127.0.0.1'],
                "LIVE_HOSTNAME": "127.0.0.1",
                "DB_PASS": "vagrant", # Live database password
                "ADMIN_PASS": "vagrant", # Live admin user password

                # application settings
                "SITENAME": "Default", # your sitename goes here
                "VIRTUALENV_HOME":  "/home/vagrant", # Absolute remote path for virtualenvs
                "PROJECT_NAME": "", # Unique identifier for project
                "REQUIREMENTS_PATH": "requirements/requirements.txt", # Path to pip requirements, relative to project
                "GUNICORN_PORT": 8001, # Port gunicorn will listen on
                "LOCALE": "en_US.UTF-8", # Should end with ".UTF-8"
                "REPO_URL": "", # Git or Mercurial remote repo URL for the project
                "LINUX_DISTRO": "squeeze", # Debian 6
            },
            ... other deployment settings ...
        }

### deploy/vagrant_settings.py

This is a copy of `local_settings.py` that will be pushed to the Vagrant instance. The configuration for this file is:

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

        # Mezzanine settings
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTOCOL", "https")

        CACHE_MIDDLEWARE_SECONDS = 60

        CACHE_MIDDLEWARE_KEY_PREFIX = "%(proj_name)s"

        # Caches are disabled for vagrant.
        CACHES = {
            'default': {
                'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
            }
        }

        # Since Vagrant is running on your computer, you can turn on debugging.
        DEBUG = True

        SESSION_ENGINE = "django.contrib.sessions.backends.cache"

        # Django 1.5+ requires a set of allowed hosts
        ALLOWED_HOSTS = [%(allowed_hosts)s]

        # Celery configuration (if django-celery is installed in requirements/requirements.txt)
        BROKER_URL = 'amqp://%(proj_name)s:%(admin_pass)s@127.0.0.1:5672/%(proj_name)s'

        # We don't need to report any crashes to an outside server.
        RAVEN_CONFIG = {}

        ...

Release Notes
-------------

### Tested Environments

I tested the script with the following configurations:

* Debian 6 and Postgresql 9.2
* Debian 6 and Postgresql 8.4 (deprecated)

### Configuration Issues

* Some fabric settings are duplicated but aren't used.

### Deploy Issues

* If more than one database server is specified, multiple projects should not be hosted on the same server. Archiving, restoring, and *Streaming Replication* are global settings for each master-slave databse setup.

* If the script fails in `fab deploy.all` because your project database already exists (i.e., an upgrade), you can complete the upgrade with `fab deploy.create:True deploy.deploy`.

* Automatic failover is not implemented. If the master database fails, manually configure a slave database as the master.

* If a host is removed from `APPLICATION_HOSTS`, `CRON_HOSTS`, or `DATABASE_HOSTS`, you have to manually remove that host entry from the Postgresql database configuration files.

### Vagrant Issues

* Vagrant deployment does not run the cron task or nginx in the virtual machine.

* Vagrant will use the repository copy of `vagrant_settings.py` and `manage.py` for your Django project. Local changes
  to the database and celery tasks will not take effect until `fab deploy.vagrant deploy.up` or `fab deploy.vagrant deploy.deploy` is run.

* To use `local_settings.py` and the working (non-repository) copy, prefix all your tasks with `fab deploy.working`. The vagrant_settings.py configuration is used.

* *NEVER* specify `VIRTUALENV_HOME` as the vagrant directory because it *will erase your local project*.

* Database changes aren't persisted when a Vagrant instance is destroyed.

* When running the script with vagrant, the following error might be shown: `Host key for server 127.0.0.1 does not match!`. The reason is another vagrant instance that you previously created. Remove the entry 127.0.0.1 from `~/.ssh/known_hosts` to fix.

* If multiple virtual machines are running and the previous instance hasn't been shut down, then you'll have to stop the previous VM manually. When using Vagrant with VirtualBox, these commands are:
  1. `VBoxManage list runningvms`
  2. `VBoxManage controlvm your_vm_name poweroff`
  3. `VBoxManage unregistervm your_vm_name --delete`

