import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() in ('true', '1', 't')
    print("=" * 65)
    print("  MedTrack - Cloud-Based Healthcare Management System")
    print(f"  Running locally at: http://localhost:{port}")
    print("  Debug mode: Auto-reloads on file changes")
    print("=" * 65)
    app.run(host=host, port=port, debug=debug)
