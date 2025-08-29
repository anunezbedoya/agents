from flask import Flask
from controllers.agent_controller import agent_bp

app = Flask(__name__)

# registra el blueprint
app.register_blueprint(agent_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)