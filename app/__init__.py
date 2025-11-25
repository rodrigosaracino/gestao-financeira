from flask import Flask
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config
from app.models import db

migrate = Migrate()
login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    # Configurar Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor, faça login para acessar esta página.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # Registrar blueprints
    from app import routes, auth
    app.register_blueprint(routes.bp)
    app.register_blueprint(auth.auth)

    return app
