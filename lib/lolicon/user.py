DEFAULT_PERMISSIONS = {
    'ping': False,
    'kudos': False,
    'use_tags': True,
    'modify_tags': False,
    'upload': False,
    'kick': False,
    'ban': False,
}

class User:

    def __init__(self, id=None, permissions=None):
        self.id = id
        self.permissions = permissions

    def has_permission(self, permission):
        if permission in self.permissions:
            return self.permissions[permission]

        return DEFAULT_PERMISSIONS[permission]
