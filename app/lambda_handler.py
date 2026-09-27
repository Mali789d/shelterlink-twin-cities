"""AWS Lambda entry point for API Gateway HTTP API payload v2."""

from mangum import Mangum

from .main import app

handler = Mangum(app, lifespan="off")
