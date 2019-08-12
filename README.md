## Prerequisites
- You have registered your app on DID sidechain. If not, you can do so at [https://elastos.academy/did-wizard/](https://elastos.academy/did-wizard/)
- You have a mysql database service running

## How to run
- `cp .env.dist didauth/.env` and edit didauth/.env to your own settings
- `pip install -t vendorlib -r requirements.txt`
- `./run.sh`