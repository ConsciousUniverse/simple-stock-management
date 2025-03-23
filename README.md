# Simpler Stock Management (Beta)

Simpler Stock Management is a web application designed to help manage warehouse and shop stock efficiently. The application provides features for searching, sorting, updating, and transferring stock items between the warehouse and shops. Data is stored in a local SQLite3 database.

Note, this is an early beta release. It is intended for testing only, and is not yet suitable for production deployment.

This is an entire rewrite of the earlier (pre-V5) 'Simple Stock Management' app, from scratch. Little-used functionality has been removed and the code is now simpler and [more maintainable](#what-changed). The earlier legacy version is now unmaintained, however the code may still be accessed in the [legacy_v4 branch](https://github.com/consciousuniverse/simple-stock-management/tree/legacy_v4).

## Security

This app has not been audited for security and probably does contain vulnerabilities that could expose data contained on the host system to unauthorized manipulation or disclosure. 
Deploy at your own risk and on a server that has *NO ACCESS* to your primary systems, or indeed any system where compromise could reveal personally identifiable information or other sensitive data. For example, a standalone VPS machine. Please also remember to remotely *BACK UP* the sqlite database.

In addition, regular updates of Python dependencies to the latest versions is necessary, to ensure patching of any discovered vulnerabilities (this may be achieved through your python package manager, such as pip or pipenv).

## Features

### User Authentication
- **Login/Logout**: Users can log in and log out of the application.
- **User Status**: Displays the logged-in user's status.
- **Brute Force Protection**: Manager & shop user logins protected from brute-force login attempts.

### Stock Management
- **Warehouse Stock**: View and manage items in the warehouse.
- **Shop Stock**: View items available in the shop.
- **Transfers Pending**: View and manage pending stock transfers.

### Search and Sort
- **Search**: Search for items in the warehouse and shop by SKU, description, or other attributes.
- **Sort**: Sort items by SKU, description, retail price, or quantity.

### Update Mode
- **Toggle Update Mode**: Managers can enter and leave update mode to make changes to item details.
- **Update Items**: Managers can update item descriptions, retail prices, and quantities.
- **Delete Items**: Managers can delete items from the warehouse stock.

### Transfer Items
- **Transfer Items**: Shop users can request to transfer items from the warehouse to the shop.
- **Complete Transfers**: Managers can dispatch or cancel pending transfers from the warehouse to the shops. Warehouse inventory is only reduced - and shop inventory increased - after managers have actioned the dispatch on the system.

## Live demo

Coming soon...

## Screenshots

### Warehouse manager's view
![image](https://github.com/user-attachments/assets/6fdf98ef-eee9-434b-84a9-a07df88dd34b)


### Shop view
![image](https://github.com/user-attachments/assets/27f0481b-a14f-45ac-9bb0-b5f304df28d9)


## What changed?

The backend is still Django Rest Framework, while the frontend is now plain old jQuery, rather than relying on ReactJS with all its dependencies. The frontend is now integrated into the Django app, as opposed to the previous standalone frontend UI.

## Installation

- Clone the repo.
- Install the python dependences. This project uses pipenv to install in a virtual environment, but a requirements.txt file has also been generated for pip install.
- Copy .env_default to .env.
- Configure the .env file you just copied. Be sure to set debug to False if publicly accessible, and configure your allowed hosts correctly.
- Generate a Django secret key with this one-liner: `python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'`.
- Set up your web server and gunicorn.
- Do the database migrations, i.e., from the project root run: `python manage.py makemigrations`, then `python manage.py migrate`.
- Create the superuser, i.e., from the project root run: `python manage.py createsuperuser`.
- Login to the admin section with your superuser (e.g., https://your-site.domain/admin) and create your warehouse manager user and shop users.
- Still in the admin section, create the 'managers' and 'shop_users' user groups.
- Assign the warehouse manager user to the 'managers' group and the shop users to the 'shop_users' group.
- Apply appropriate brute-force mitagions to your server, to protect the login (e.g., fail2ban).

Remeber not to host the app on a server containing any personal or other sensitive information, as it has not been vetted for security, and cannot be considered secure!

## License

Simpler Stock Management is licensed under the GPLv3. See the [LICENSE](LICENSE) file for more details.

## Author

Dan Bright - [GitHub](https://github.com/consciousuniverse), github@bright.contact
