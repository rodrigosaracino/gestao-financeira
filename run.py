import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # Debug apenas quando explicitamente pedido (nunca em produção)
    debug = os.environ.get('FLASK_DEBUG') == '1'
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    app.run(debug=debug, host=host, port=8000)
