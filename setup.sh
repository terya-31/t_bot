#!/bin/bash
pip install --upgrade pip
pip install --index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple t-tech-investments==1.49.0
pip install python-dotenv grpcio protobuf sentry-sdk python-dateutil cachetools==5.5.2 deprecation aiohttp aiohttp-socks requests