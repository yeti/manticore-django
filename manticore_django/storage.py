from cumulus.settings import CUMULUS
from cumulus.storage import CloudFilesStorage
from random import choice


__author__ = 'rudy'

class MultiContainerCloudFilesStorage(CloudFilesStorage):
    """
    Custom storage for Rackspace Cloud Files.
    """
    active_containers = CUMULUS['ACTIVE_CONTAINERS']
    all_containers = CUMULUS['ALL_CONTAINERS']

    def _open(self, name, mode='rb'):
        name = self.set_current_container(name)
        return super(MultiContainerCloudFilesStorage, self)._open(name, mode)

    def _save(self, name, content):
        name = super(MultiContainerCloudFilesStorage, self)._save(name, content)
        return "%s/%s" % (self.container.name, name)

    def delete(self, name):
        name = self.set_current_container(name)
        return super(MultiContainerCloudFilesStorage, self).delete(name)

    def exists(self, name):
        self.set_random_container()
        return super(MultiContainerCloudFilesStorage, self).exists(name)

    def size(self, name):
        name = self.set_current_container(name)
        return super(MultiContainerCloudFilesStorage, self).size(name)

    def url(self, name):
        name = self.set_current_container(name)
        return super(MultiContainerCloudFilesStorage, self).url(name)

    def modified_time(self, name):
        name = self.set_current_container(name)
        return super(MultiContainerCloudFilesStorage, self).modified_time(name)

    def set_current_container(self, name):
        """
        Set the current container based on the first folder portion of 'name'
        """
        container_name, separator, new_name = name.partition("/")
        if container_name in self.all_containers:
            if self.container.name != container_name:
                self.container = self.connection.get_container(container_name)
                if hasattr(self, '_container_public_uri'):
                    delattr(self, '_container_public_uri')
            return new_name
        else:  # Else we need to use the default container
            if self.container.name != self.container_name:
                self.container = self.connection.get_container(self.container_name)
                if hasattr(self, '_container_public_uri'):
                    delattr(self, '_container_public_uri')
            return name

    def set_random_container(self):
        """
        Set the container to a random container for load balancing
        """
        self.container = self.connection.get_container(choice(self.active_containers))
        if hasattr(self, '_container_public_uri'):
            delattr(self, '_container_public_uri')