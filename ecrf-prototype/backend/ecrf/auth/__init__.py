"""Who is asking, and what are they allowed to do.

permissions.py  one table from role to permissions, and the require()
                dependency that every endpoint uses
scope.py        which rows a user may see; outside the scope is 404
passwords.py    scrypt hashing with no extra dependency
sessions.py     cookie sessions and the login rate limit
"""
