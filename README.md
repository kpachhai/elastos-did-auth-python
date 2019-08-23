## Prerequisites
- You have registered your app on DID sidechain. If not, you can do so at [https://elastos.academy/did-wizard/](https://elastos.academy/did-wizard/)
- You have a mysql database service running. If you want to run a simple mysql database on a docker container, make sure to install docker first and then execute `docker run --name did-auth-mysql -e MYSQL_ROOT_PASSWORD=12345678 -e MYSQL_DATABASE=did-auth -p 0.0.0.0:3306:3306/tcp -d mysql:5.7`

## How to run
- `cp .env.dist didauth/.env` and edit didauth/.env to your own settings
- `pip install -t vendorlib -r requirements.txt`
- `./run.sh`
- Open "http://localhost:5000/" on your browser. The home page looks like the following:
![Home Page](./github_images/home.png)