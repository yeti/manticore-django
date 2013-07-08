from genericpath import exists
from fabric.context_managers import cd, settings
from fabric.contrib.console import confirm
from fabric.contrib.files import sed, _expand_path
from fabric.state import env
from fabric.decorators import task, roles
from fabric.operations import local, os, get, put
from fabric.tasks import execute
from utils import log_call, pip, project, activate_venv
from deploy import vagrant, install_prereq, installdb, fix_db_permissions, installapp, copy_db_ssh_keys, create_prereq, removeapp, run, sudo, manage, create_rabbit, createdb, createapp2

__author__ = 'rudy'


# Assumes you're running this in your new project's folder already
@task
@log_call
def new(project_name='', app_name='', db_password='', repo_url=''):
    if len(project_name) == 0 or len(app_name) == 0 or len(db_password) == 0 or len(repo_url) == 0:
        print "Usage: fab new:<project_name>,<app_name>,<db_password>,<repo_url>"
        print ""
        print "Common usage:"
        print "            <project_name> should be different than <app_name>"
        return

    # ensure that project_name and app_name are different
    if project_name == app_name and not confirm("Your app_name is the same as the project_name. They should be different. Continue?"):
        return

    # If a Vagrantfile exists this means a set up was already tried
    if exists("Vagrantfile"):
        if not confirm("Vagrant file already exists, continue anyways?"):
            return
    else:
        local("vagrant init debian-squeeze http://dl.dropbox.com/u/54390273/vagrantboxes/Squeeze64_VirtualBox4.2.4.box")
        local("sed 's/# config.vm.network :forwarded_port, guest: 80, host: 8080/config.vm.network :forwarded_port, guest: 8000, host: 8000/g' Vagrantfile > Vagrantfile.tmp")
        local("mv Vagrantfile.tmp Vagrantfile")

    local("vagrant up")

    # Create a fake settings file for access to vagrant
    local("cp %s/fabric_settings.py settings.py" % os.path.dirname(os.path.realpath(__file__)))
    env.settings = __import__("settings", globals(), locals(), [], 0).FABRIC
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
    execute(create_project)

    # Remove temp settings and change local working path permanently into project folder so we can copy deploy templates
    local("rm settings.py settings.pyc")
    os.chdir(env.proj_name)

    # Finish setting up the database and copy over appropriate templates
    createdb(True)
    execute(createapp2)
    execute(create_rabbit, True)
    execute(init_db)
    execute(init_git)


@roles('application')
def create_virtualenv():
    with cd(env.venv_home):
        if exists(env.proj_name):
            if not confirm("Virtualenv exists: %s\n Do you want to replace it?" % env.proj_name):
                print "\nAborting!"
                return False
            removeapp()
        sudo("virtualenv %s --distribute" % env.proj_name)


@roles('application')
def create_project():
    pip("mezzanine")

    with activate_venv():
        # /vagrant is the shared mounted folder between vagrant and your local filesystem
        with cd("/vagrant"):
            sudo("mezzanine-project %s" % env.proj_name)

    with project():
        sudo("pip freeze > requirements/requirements.txt")

        sudo("%s startapp %s" % (env.manage, env.app_name))

        get("settings.py", "remote_settings.py")
        Helper().add_line_to_list("remote_settings.py", "settings.py.tmp", "INSTALLED_APPS = (", '    "%s",' % env.app_name)
        put("settings.py.tmp", "settings.py", use_sudo=True)
        put("%s/vagrant_settings.py" % os.path.dirname(os.path.realpath(__file__)), "deploy/vagrant_settings.py", use_sudo=True)

        # Add the appropriate fabric settings for local and development deployment
        with open("%s/fabric_settings.py" % os.path.dirname(os.path.realpath(__file__))) as f:
            file_path = _expand_path("settings.py")
            sudo("echo '%s' >> %s" % ("", file_path))
            for line in f:
                sudo("echo '%s' >> %s" % (line.rstrip('\n').replace("'", r"'\\''"), file_path))

        # Set fabric settings according to user's input
        sed("settings.py", "\"DB_PASS\": \"vagrant\"", "\"DB_PASS\": \"%s\"" % env.db_pass, use_sudo=True, backup="", shell=True)
        sed("settings.py", "\"DB_PASS\": \"\"", "\"DB_PASS\": \"%s\"" % env.db_pass, use_sudo=True, backup="", shell=True)
        sed("settings.py", "\"PROJECT_NAME\": \"\"", "\"PROJECT_NAME\": \"%s\"" % env.proj_name, use_sudo=True, backup="", shell=True)
        sed("settings.py", "\"REPO_URL\": \"\"", "\"REPO_URL\": \"%s\"" % env.repo_url, use_sudo=True, backup="", shell=True)
        sed("settings.py", "\"PROJECT_PATH\": \"\"", "\"PROJECT_PATH\": \"%s\"" % env.proj_path, use_sudo=True, backup="", shell=True)

        # We will be using the manticore fabfile not Mezzanine's
        sudo("rm fabfile.py")

        #TODO: Install and Link manticore-django fabfile package?

    local("rm settings.py.tmp remote_settings.py")


@roles('application')
def init_db():
    with project():
        manage("syncdb --noinput")
        manage("schemamigration %s --initial" % env.app_name)
        manage("migrate")


@roles('application')
def init_git():
    with project():
        run("git init")
        run("echo '.idea/' >> .gitignore")
        run("git add .")
        run("git commit -m'init'")
        with settings(warn_only=True):
            run("git remote add unfuddle %s" % env.repo_url)
            run("git config remote.unfuddle.push refs/heads/master:refs/heads/master")
        run("git push unfuddle master")


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


## Copy Existing Project ##
#1 create the vagrant box

#2 manticore-django install then deploy routine

#3 PyCharm settings

## Future ##
# installing new requirements
# running new migrations