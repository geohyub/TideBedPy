"""pytest conftest - tidebedpy 모듈 경로 설정."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tidebedpy'))
