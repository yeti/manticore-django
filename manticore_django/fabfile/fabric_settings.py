FABRIC = {
    "vagrant": {
        "SSH_USER": "vagrant", # SSH username
        "SSH_PASS": "vagrant", # SSH password (consider key-based authentication)
        "SSH_KEY_PATH": "", # Local path to SSH key file, for key-based auth

        # deployment SSH key
        "DEPLOY_MY_PUBLIC_KEY": "~/.ssh/id_rsa.pub",
        "DEPLOY_SSH_KEY_PATH": "",
        "DEPLOY_DB_CLUSTER_SSH_KEY_PATH": "",

        "APPLICATION_HOSTS": ['127.0.0.1:2222'],
        "PRIVATE_APPLICATION_HOSTS": ['127.0.0.1'],
        "DATABASE_HOSTS": ['127.0.0.1:2222'],
        "PRIVATE_DATABASE_HOSTS":['127.0.0.1'],
        "LIVE_HOSTNAME": "127.0.0.1",
        "DB_PASS": "vagrant", # Live database password
        "ADMIN_PASS": "vagrant", # Live admin user password

        # shared application settings
        "SITENAME": "Default",
        "VIRTUALENV_HOME": "/home/vagrant", # Absolute remote path for virtualenvs
        "PROJECT_NAME": "", # Unique identifier for project
        "PROJECT_PATH": "",
        "REQUIREMENTS_PATH": "requirements.txt", # Path to pip requirements, relative to project
        "GUNICORN_PORT": 8001, # Port gunicorn will listen on
        "LOCALE": "en_US.UTF-8", # Should end with ".UTF-8"
        "REPO_URL": "", # Git or Mercurial remote repo URL for the project
        "LINUX_DISTRO": "wheezy",
    },
    "development": {
        "SSH_USER": "root", # SSH username
        "SSH_PASS": "", # SSH password (consider key-based authentication)
        "SSH_KEY_PATH": "", # Local path to SSH key file, for key-based auth

        # deployment SSH key
        "DEPLOY_MY_PUBLIC_KEY": "~/.ssh/id_rsa.pub",
        "DEPLOY_SSH_KEY_PATH": "",
        "DEPLOY_DB_CLUSTER_SSH_KEY_PATH": "",

        # Yeti sandbox
        "APPLICATION_HOSTS": ['127.0.0.1'], # List of hosts to deploy to
        "DATABASE_HOSTS": ['127.0.0.1'],
        "LIVE_HOSTNAME": "", # Host for public site.
        "DB_PASS": "", # Live database password
        "ADMIN_PASS": "admin", # Live admin user password

        # shared application settings
        "SITENAME": "Default",
        "VIRTUALENV_HOME": "/root/envs", # Absolute remote path for virtualenvs
        "PROJECT_NAME": "", # Unique identifier for project
        "REQUIREMENTS_PATH": "requirements.txt", # Path to pip requirements, relative to project
        "GUNICORN_PORT": 8001, # Port gunicorn will listen on
        "LOCALE": "en_US.UTF-8", # Should end with ".UTF-8"
        "REPO_URL": "", # Git or Mercurial remote repo URL for the project
        "LINUX_DISTRO": "wheezy",
    }
}