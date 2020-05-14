import sys
from genericpath import exists
from importlib import import_module
from fabric.context_managers import cd, settings
from fabric.contrib.console import confirm
from fabric.contrib.files import sed, _expand_path, exists as remote_exists
from fabric.state import env
from fabric.decorators import task, roles
from fabric.operations import local, os, get, put
from fabric.tasks import execute
from utils import log_call, pip, project, activate_venv, virtualenv
from deploy import vagrant, install_prereq, installdb, fix_db_permissions, installapp, copy_db_ssh_keys, create_prereq, removeapp, run, sudo, manage, create_rabbit, createdb, createapp2, up
from fabric.contrib.files import append

__author__ = 'rudy'


# Assumes you're running this in your new project's folder already
@task
@log_call
def new(project_name='', app_name='', db_password='', repo_url='', is_new=''):
    if len(project_name) == 0 or len(app_name) == 0 or len(db_password) == 0 or len(repo_url) == 0:
        print "Usage: fab new:<project_name>,<app_name>,<db_password>,<repo_url>,<is_new>"
        print ""
        print "Common usage:"
        print "            <project_name> should be different than <app_name>"
        return

    # triggers usage of the new django file-structure
    if is_new and is_new == 'True':
        is_new = True

    # ensure that project_name and app_name are different
    if project_name == app_name and not confirm("Your app_name is the same as the project_name. They should be different. Continue?"):
        return

    if not create_vagrantfile():
        return False

    # Add the current directory to our sys path so we can import fabric_settings
    sys.path.append(os.getcwd())

    # Create a fake settings file for access to vagrant
    local("cp %s/fabric_settings.py fabric_settings.py" % os.path.dirname(os.path.realpath(__file__)))
    env.settings = __import__("fabric_settings", globals(), locals(), [], 0).FABRIC
    vagrant()

    # Set appropriate settings from inputs
    env.proj_path = "/vagrant/%s" % project_name
    env.proj_name = project_name
    env.venv_path = "%s/%s" % (env.venv_home, env.proj_name)
    env.db_pass = db_password
    env.app_name = app_name
    env.manage = "%s/bin/python /vagrant/%s/manage.py" % (env.venv_path, env.proj_name)
    env.repo_url = repo_url


    # Set up vagrant box with appropriate system packages
    execute(install_prereq)
    execute(installdb)
    execute(fix_db_permissions)
    execute(installapp)
    execute(copy_db_ssh_keys)

    # Set up a virtualenv and mezzanine project
    execute(create_prereq)
    execute(create_virtualenv)
    execute(create_project, is_new=is_new)

    # Remove temp settings and change local working path permanently into project folder so we can copy deploy templates
    local("rm fabric_settings.py fabric_settings.pyc")
    os.chdir(env.proj_name)

    # Finish setting up the database and copy over appropriate templates
    createdb(True)
    execute(createapp2, is_new=is_new)
    execute(create_rabbit, True)
    execute(init_db)
    execute(init_git)


# Assumes you're running this in your new project's folder already
@task
@log_call
def clone(repo_url=''):
    if len(repo_url) == 0:
        print "Usage: fab new:<repo_url>"
        return

    if not create_vagrantfile():
        return False

    # We'll create a temporary copy to get the appropriate settings for deployment
    if exists("temp"):
        if not confirm("This project already exists, continue anyways?"):
            return False
    else:
        local("mkdir temp")
        local("git clone %s temp/." % repo_url)

    #TODO: We still won't have any vagrant_settings.py or FABRIC in settings.py after we deploy and delete temp
    # Check to see if this project is ready for vagrant deployment - if not we'll 'upgrade' it
    if not exists("temp/deploy/vagrant_settings.py"):
        local("cp %s/vagrant_settings.py temp/deploy/vagrant_settings.py" % os.path.dirname(os.path.realpath(__file__)))

    # Add the current directory to our sys path so we can import fabric_settings
    sys.path.append(os.getcwd())

    os.chdir("temp")
    sys.path.append(os.getcwd())

    #TODO: Auto add fabric_settings.py if it doesn't exist
    # fabric_settings = import_module("fabric_settings")
    fabric_settings = __import__("fabric_settings", globals(), locals(), [], 0)

    #TODO: Auto add vagrant to fabric_settings.py if it doesn't exist
    env.settings = fabric_settings.FABRIC
    if 'vagrant' not in env.settings:
        print 'Please set up "vagrant" mode in fabric_settings.py and rerun this command'
        return False

    # And we're ready to go
    up()

    # Now clean up temporary copy
    os.chdir("..")
    local("rm -rf temp")


@task
@log_call
def create_vagrantfile():
    # If a Vagrantfile exists this means a set up was already tried
    if exists("Vagrantfile"):
        if not confirm("Vagrant file already exists, continue anyways?"):
            return False
    else:
        local("vagrant init wheezy https://www.dropbox.com/s/t22df7cl0xoiv3t/debian-7.2.0.box?dl=1")
        # TODO: `:forwarded_port` is now "forwarded_port" with new version of vagrant
        local("sed 's/# config.vm.network \"forwarded_port\", guest: 80, host: 8080/config.vm.network \"forwarded_port\", guest: 8000, host: 8000/g' Vagrantfile > Vagrantfile.tmp")
        local("mv Vagrantfile.tmp Vagrantfile")

        local("sed 's/# config.ssh.forward_agent = true/config.ssh.forward_agent = true/g' Vagrantfile > Vagrantfile.tmp")
        local("mv Vagrantfile.tmp Vagrantfile")

    running_vms = local("VBoxManage list runningvms", capture=True)
    if running_vms != '':
        print running_vms
        if not confirm("A virtual machine is already running, continue?"):
            return False

    local("vagrant up")
    return True


@roles('application')
def create_virtualenv():
    with cd(env.venv_home):
        if exists(env.proj_name):
            if not confirm("Virtualenv exists: %s\n Do you want to replace it?" % env.proj_name):
                print "\nAborting!"
                return False
            removeapp()
        run("virtualenv %s --distribute" % env.proj_name)


@roles('application')
def create_project(is_new=False):
    pip("django mezzanine pep8 pyflakes django-model-utils")

    with activate_venv():
        # /vagrant is the shared mounted folder between vagrant and your local filesystem
        with cd("/vagrant"):
            sudo("mezzanine-project %s" % env.proj_name)

    with project():
        sudo("pip freeze > requirements.txt")

        sudo("%s startapp %s" % (env.manage, env.app_name))

        settings_path = "settings.py"
        if is_new:
            settings_path = "{}/{}".format(env.proj_name, settings_path)

        get(settings_path, "remote_settings.py")
        Helper().add_line_to_list("remote_settings.py", "settings.py.tmp", "INSTALLED_APPS = (", '    "%s",' % env.app_name)
        put("settings.py.tmp", "settings.py", use_sudo=True)
        sed("settings.py", "USE_SOUTH = True", "USE_SOUTH = False", use_sudo=True, backup="", shell=True)
        put("%s/vagrant_settings.py" % os.path.dirname(os.path.realpath(__file__)), "deploy/vagrant_settings.py", use_sudo=True)
        put("%s/celeryd.conf" % os.path.dirname(os.path.realpath(__file__)), "deploy/celeryd.conf", use_sudo=True)

        # Add the appropriate fabric settings for local and development deployment
        put("fabric_settings.py", "fabric_settings.py", use_sudo=True)
        with open("%s/fabric_import.py" % os.path.dirname(os.path.realpath(__file__))) as f:
            file_path = _expand_path("settings.py")
            sudo("echo '%s' >> %s" % ("", file_path))
            for line in f:
                sudo("echo '%s' >> %s" % (line.rstrip('\n').replace("'", r"'\\''"), file_path))

        # Set fabric settings according to user's input
        sed("fabric_settings.py", "\"DB_PASS\": \"vagrant\"", "\"DB_PASS\": \"%s\"" % env.db_pass, use_sudo=True, backup="", shell=True)
        sed("fabric_settings.py", "\"DB_PASS\": \"\"", "\"DB_PASS\": \"%s\"" % env.db_pass, use_sudo=True, backup="", shell=True)
        sed("fabric_settings.py", "\"PROJECT_NAME\": \"\"", "\"PROJECT_NAME\": \"%s\"" % env.proj_name, use_sudo=True, backup="", shell=True)
        sed("fabric_settings.py", "\"REPO_URL\": \"\"", "\"REPO_URL\": \"%s\"" % env.repo_url, use_sudo=True, backup="", shell=True)
        sed("fabric_settings.py", "\"PROJECT_PATH\": \"\"", "\"PROJECT_PATH\": \"%s\"" % env.proj_path, use_sudo=True, backup="", shell=True)

        # We will be using the manticore fabfile not Mezzanine's
        sudo("rm fabfile.py")

        # Change Mezzanine project to be compatible with this fabfile
        sed("deploy/local_settings.py.template", "\"HOST\": \"127.0.0.1\"", "\"HOST\": \"%s\"" % "%(primary_database_host)s", use_sudo=True, backup="", shell=True)
        append("deploy/local_settings.py.template", "\n# Django 1.5+ requires a set of allowed hosts\nALLOWED_HOSTS = [%(allowed_hosts)s]\n\n# Celery configuration (if django-celery is installed in requirements/requirements.txt)\nBROKER_URL = 'amqp://%(proj_name)s:%(admin_pass)s@127.0.0.1:5672/%(proj_name)s'\n\n")


        #TODO: Install and Link manticore-django fabfile package?

        run("cp deploy/local_settings.py.template deploy/development_settings.py")
        run("cp deploy/local_settings.py.template deploy/staging_settings.py")
        run("cp deploy/local_settings.py.template deploy/feature_staging_settings.py")
        run("cp deploy/local_settings.py.template deploy/production_settings.py")
        run("rm deploy/local_settings.py.template")

    local("rm settings.py.tmp remote_settings.py")


@roles('application')
def init_db():
    with project():
        with settings(warn_only=True):
            manage("syncdb --noinput")
            manage("migrate")


@roles('application')
def init_git():
    local("git init")
    local("echo '.idea/' >> .gitignore")
    local("echo 'last.commit' >> .gitignore")
    local("echo 'gunicorn.pid' >> .gitignore")
    local("git add .")
    local("git commit -m'init'")

    with settings(warn_only=True):
        local("git remote add origin %s" % env.repo_url)
        local("git config remote.origin.push refs/heads/master:refs/heads/master")
    local("git push origin master")


@task
@roles("application")
def create_compressor():
    sudo("apt-get install -y -q g++ make checkinstall")

    if not remote_exists("~/src", use_sudo=True):
        sudo("mkdir ~/src")

    with cd("~/src"):
        sudo("wget -N http://nodejs.org/dist/v0.10.13/node-v0.10.13.tar.gz")
        sudo("tar xzvf node-v0.10.13.tar.gz")

        with cd("node-v0.10.13"):
            sudo("./configure")
            #TODO: Currently prompts you to fill out documentation and change node version number
            sudo("checkinstall")
            sudo("dpkg -i node_*")

    sudo("npm install -g less")

@task
@log_call
def pip_install():
    """Runs pip install"""
    env.settings = __import__("fabric_settings", globals(), locals(), [], 0).FABRIC
    print env.settings
    vagrant()
    execute(pip_install_task)


@roles("application")
def pip_install_task():
    with virtualenv():
        sudo("pip install -r %s/%s" % (env.proj_path, env.reqs_path))


class Helper:
    def add_line_to_list(self, read_file, write_file, list, insert_line):
        f = open(read_file, "r")
        g = open(write_file, "w")

        state = 0
        # 0 - beginning of file
        # 1 - inside the list
        # 2 - after the list

        line = f.readline()
        while len(line) > 0: # a zero-length line defines end of file
            if state == 0:
                if line.find(list) == 0: # identified the start list
                    state = 1
            elif state == 1:
                if line.find(")") == 0: # identified the end list
                    # add in the inserted line here
                    g.write("%s\n" % insert_line)
                    state = 2

            # write the line as is
            g.write(line)

            # read the next line
            line = f.readline()

        g.close()
        f.close()
