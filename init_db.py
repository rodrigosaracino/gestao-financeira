#!/usr/bin/env python3
"""
Inicializa o banco e aplica as migrações pendentes.
Roda em todo start do container (docker-compose), então precisa ser idempotente.
"""
import os

import sqlalchemy as sa
from flask_migrate import stamp, upgrade

from app import create_app
from app.models import db

# Última migração que o db.create_all() antigo já cobria por completo.
REVISAO_BASE = '5b19b8709657'


def init_database():
    app = create_app()
    with app.app_context():
        db.create_all()  # cria tabelas que ainda não existem

        migracoes = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')
        if os.path.isdir(os.path.join(migracoes, 'versions')):
            insp = sa.inspect(db.engine)
            versionado = False
            if 'alembic_version' in insp.get_table_names():
                with db.engine.connect() as c:
                    versionado = c.execute(sa.text('SELECT count(*) FROM alembic_version')).scalar() > 0
            if not versionado:
                # banco criado via create_all: marca a base e aplica só o que é novo
                stamp(directory=migracoes, revision=REVISAO_BASE)
            upgrade(directory=migracoes)
        print('Banco de dados pronto.')


if __name__ == '__main__':
    init_database()
