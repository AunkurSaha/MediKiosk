import sys; print(sys.path); sys.path.insert(0, '/c/MEDIKIOSK/backend'); print(sys.path); from app.main import app; print('ok')
