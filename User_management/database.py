from infra.auth_repository_mysql import AuthRepositoryMySQL
from infra.config_repository import ConfigRepository


_auth_repo = AuthRepositoryMySQL(ConfigRepository("config.json"))


def create_table():
    _auth_repo.check_schema()


def add_user(nombre, contraceña):
    return _auth_repo.create_cashier(nombre, contraceña)


def get_user(nombre, contraceña):
    return _auth_repo.authenticate_cashier(nombre, contraceña)