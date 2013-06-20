manticore-django
================

Utility functionality for a Manticore Django project

Deployment script
-----------------
Manticore-django comes with a `fabric` deployment script. The script is based on Mezzanine's deployment script with additional features.
These features allow the script to deploy an *application* and *database* server using different `settings.py`.

Setup for:

* Topologies
  * Single application/cron/database server
  * Multiple independent application servers
  * Multiple independent cron servers (cron servers are identical to application servers with cron processes enabled)
  * Master and slave Postgres server with Streaming Replication
* Different targets aptly named *development*, *staging*, *production*, and *vagrant*.
* Vagrant+Pycharm support -- doesn't run nginx, cron, or gunicorn

Out of the box features:

* RabbitMQ asynchronous background task queue
* Celery support
* Copy your SSH public key to the server
* Copy your repository's private key to the server
* Copy database public/private keys on each database peer

### Requirements

These requirements should be listed in your `pip` requirements file:

* Django 1.5 or higher
* Mezzanine 1.4.3 or higher
* `fabric`
* `simplejson`
* django-celery (optional)

### Usage Scenario

1. First, a valid installation of Python 2.6 or higher must be installed on your computer. Installing Python is specific to your operating system.

2. Optionally, virtualenvwrapper should be installed on your computer to keep Python projects separate: `pip install virtualenv`

3. Fabric, a deployment scripting tool, must be installed: `pip install fabric`

4. Your `settings.py` file has to be configured properly. See next section for details.

5. If this is a first time installation: (a) replace Mezzanine's fabric script with the one in this repository; (b) create `deploy/development_settings.py`, `deploy/production_settings.py`, `deploy/staging_settings.py`, and/or `deploy/vagrant_settings.py`; and (c) add `deploy/celeryd.conf`. The contents of these files are presented below.

Your directory structure should look like:

* deploy
  * celeryd.conf
  * crontab
  * development_settings.py
  * gunicorn.conf.py
  * nginx.conf
  * production_settings.py
  * staging_settings.py
  * supervisor.conf
  * vagrant_settings.py
* fabfile.py
* manage.py
* local_settings.py
* settings.py
* urls.py
* ...

6. If you make major configuration changes, you should run `fab create:True deploy`.

7. If you are changing only source code, you should run `fab deploy` or `fab deployapp`.

Fabric Configuration
--------------------

This Fabric deploy script in Manticore-Django is a drop-in replacement for Mezzanine's fabric deployment.
In addition to Mezzanine's script, you are able to configure application, cron, and database hosts separately.

In your `settings.py` file:

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
            },
            "vagrant": {
                ... see below ...
            }
        }


### `deploy/development_settings.py`, `deploy/staging_settings.py`, and `deploy/production_settings.py`

Create server-specific settings for each of the specified targets `deploy/development_settings.py`, `deploy/staging_settings.py`, and `deploy/production_settings.py`:

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

Add this file to your deploy directory along with `crontab`, `gunicorn.conf.py`, `nginx.conf`, and
`supervisor.conf`.

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

Modes
-----

1. `fab development ...`
2. `fab staging ...`
3. `fab production ...`
4. `fab vagrant ...`
5. `fab working ...`

The **development** environment (1) is default. See the next section for (4) and (5).

If something isn't working right and you want to know why, pass in a parameter `True` to these commands.

1. `fab development:True`
2. `fab staging:True`
3. `fab production:True`
4. `fab vagrant:True`
5. `fab working:True`


Vagrant Configuration
---------------------

Usage scenario: you can use Pycharm to remotely connect to the Vagrant box for development. In development,
`nginx`, `gunicorn`, and `cron` are disabled.

1. `fab up`
2. `fab vagrant up`
3. `fab vagrant ...`
4. `fab working up`
5. `fab working ...`

(1) and (2) are equivalent of each other. Both will setup a Vagrant instance using the `"vagrant"` configuration in `FABRIC`.

(3) will allow you to issue any of the regular commands such as `deploy` and `restartapp` using Vagrant's configuration.

(4) and (5) are identical to Vagrant except that `manage.py` is run from `/vagrant/`'s directory, which is shared between
host and client, instead of the repository's copy. When Vagrant is run, `/vagrant/<proj_name>/manage.py` replaces the
one specified in `VIRTUALENV_HOME`. Make sure that you configure `BROKER_URL` if you intend to run `fab working up`.

### Setting up PyCharm

Prerequisites:

* VirtualBox
* Vagrant

Steps:

1. Configure PyCharm 2.7+ Vagrant settings to a Debian 6+ 64-bit machine
2. Set the Project Interpreter to a Remote 127.0.0.1:2222
3. Change your *Run > Configuration* to bind to host `0.0.0.0`
4. Configure `Vagrantfile` to forward guest port `8000` to a host port

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

This is a copy of `local_settings.py` that will be pushed to the server when `fab vagrant up` is called. The configuration for this

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

* Some fabric settings are duplicated but needn't.

### Server Issues

* Each project must have its own database servers. Archiving, restoring, and *Streaming Replication* are tightly coupled
  to the database server.

* If the script fails in `fab all` because your project database already exists (i.e., an upgrade), you can
  complete the upgrade with `fab create:True deploy`.

* Automatic failover is not implemented. If the master database fails, manually configure a slave database as the master.

* If a host is removed from `APPLICATION_HOSTS`, `CRON_HOSTS`, or `DATABASE_HOSTS`, you have to manually remove that
  host entry from the Postgresql database configuration files.

### Vagrant Issues

* Vagrant deployment does not run the cron task or nginx.

* Vagrant will use the repository copy of `vagrant_settings.py` and `manage.py` for your Django project. Local changes
  to the database and celery tasks will not take effect until `fab vagrant up` or `fab vagrant deploy` is run.

* To use `local_settings.py` and the working (non-repository) copy, prefix all your tasks with `fab working`.
  working uses the same FABRIC configuration as vagrant.

* *NEVER* specify `VIRTUALENV_HOME` as the vagrant directory because it *will erase your local project*.

* Database changes aren't persisted when a Vagrant instance is destroyed.
