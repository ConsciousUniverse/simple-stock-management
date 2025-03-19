# Simple Stock Management - Server Component

## NEW APP AVAILABLE

This app is now legacy, unmaintained, archived, and should not be used. A newer, more lightweight app with similar basic functionality is now available here: https://github.com/ConsciousUniverse/simpler-stock-management

## Security Advisory

Please note, this application has not been audited for security and may contain vulnerabilities that could expose data contained on the host system to unauthorized manipulation or disclosure. Deploy at your own risk and on a server that has *no* access to your primary systems, or indeed any system where compromise could reveal personally identifiable information or other sensitive data. For example, a standalone VPS machine. 

In addition, regular updates of Python dependencies to the latest versions is necessary, to ensure patching of any discovered vulnerabilities (this may be achieved through your python package manager, such as pip or pipenv).

## About

This a demo/prototype repository for the server component of the Simple Stock Management stock and inventory system. It is built using web technologies, with a client/server architecture. The repository for the frontend app component is at: https://github.com/Aninstance/simple-stock-management-frontend

The system allows "stores" to request transfers of stock ("order") from a central stock repository ("warehouse"). Stock is adjusted for the "Warehouse Account" and the "Store Account" as stock transfers are "ordered". Email notifications are sent to the "warehouse" administrator(s) and the ordering "store manager".

This project offers a web frontend that connects to a RESTful API backend. Data is stored in either a SQLite, mySQL or PostgreSQL (recommended) database.

## Support & Project Status

A regularly patched, proprietary licensed application-as-a-service version, fully maintained for subscribers and clients, is available upon request (limited availability) and is currently priced at £10.00/month.

A one-off installation service for this GPL licensed version is also available.

The GPL licensed version of this project offered here is *not guaranteed* to be regularly maintained. It is made available here for demo/prototype purposes only, and should not be used in production (i.e. a "live" working environment) unless the administrator regularly patches project dependencies (i.e. PYPI & npm packages) with upstream security updates as and when released by vendors.

If you would like to avail of the proprietary subscription to the application-as-a-service, or request other bespoke work on this project, please email to discuss: ssm@uplandsdynamic.com.

## Key Technologies for Server Component

Key technologies include: Python 3.7; Django; Django-rest-framework; Django_q (for asynchronous processes); Javascript; HTML5; CSS3;

## Live Demo

There is a live demo, available here:

https://frontend.ssm.webapps.uplandsdynamic.com

There are two test users - one for the warehouse administrator, the other for a 'store manager'. Credentials are:

Adminstrator:
Username: test_admin
Password: jduejHje(89K

Manager:
Username: test_manager
Password: jduejHje(89K

## Screenshots

![Screenshot 1](./meta/img/screenshot_1.png?raw=true)
![Screenshot 2](./meta/img/screenshot_2.png?raw=true)
![Screenshot 4](./meta/img/screenshot_4.png?raw=true)

![Screenshot 6](./meta/img/screenshot_6.png?raw=true)
![Screenshot 7](./meta/img/screenshot_7.png?raw=true)
![Screenshot 8](./meta/img/screenshot_8.png?raw=true)
![Screenshot 5](./meta/img/screenshot_5.png?raw=true)
![Screenshot 9](./meta/img/screenshot_9.png?raw=true)
![Screenshot 10](./meta/img/screenshot_10.png?raw=true)

## Key features

- Administrator may add, edit and delete stock from database.
- Store managers may request transfers ("order") stock from the "warehouse".
- Dynamic search of stock lines (SKU and description).
- Configurable pagination of results table.
- Transfer requests of stock lines are loaded to a "truck" (i.e. like "adding to a basket/cart" in an e-commerce system), before the request is submitted.
  - The "truck" retains the transfer data until the "Request truck dispatch" button is clicked. The truck data is retained across sessions (meaning the data remains in the truck even if the user logs out, then resumes their transfer at a later time).
  - Once the "Request truck dispatch" button is clicked, the transfer request process will complete. The truck empties and a single email containing a summary of the successful transfers - and any failures - is dispatched to both the requesting user and the warehouse administrator. Warehouse quantities are immediately adjusted accordingly, both in the "Warehouse" and "Store" accounts.
- A "Stock take" feature compiles and emails detailed reports, consisting of:

  - For every unique stock line in a "Store Account" (see screenshot #10, below, for an example report):

    - SKU
    - Stock description
    - Units of opening stock
    - Units of closing stock
    - Change in stock units since last stock take
    - Number of units transferred since last stock take
    - Number of units recorded sold since last stock take
    - Number of units recorded as shrinkage since last stock take
    - Differential for units of unrecorded history since last stock take (i.e. unrecorded sales, unrecorded transfers, unrecorded loss)
    - Current transfer value of a unit
    - Current retail price of a unit
    - Total value of units recorded sold since last stock take
    - Total value of units recorded as shrinkage since last stock take
    - Total value of units transferred since last stock take
    - Total value differential of units with unrecorded history since last stock take, at present xfer price
    - Total value differential of units with unrecorded history since last stock take, at present retail price (i.e. unrecorded sales, unrecorded transfers, shrinkage)
    - Current total held stock transfer value at present xfer price
    - Current total held stock retail value at present retail price

  - Overview of the entire "Store Account" (see screenshot #10, below, for an example report):

    - Units of opening stock
    - Units of closing stock
    - Units of stock transferred since last stock take
    - Units of stock recorded sold since last stock take
    - Units of stock recorded as shrinkage since last stock take
    - Change in stock holding owing to unrecorded unit history since last stock take (i.e. unrecorded sales, unrecorded transfers, unrecorded loss)
    - Value of stock recorded sold since last stock take
    - Value of stock recorded as shrinkage since last stock take
    - Total value differential of units with unrecorded history since last stock take at current transfer value
    - Total value differential of units with unrecorded history since last stock take at current retail value (i.e. unrecorded sales, unrecorded transfers, unrecorded loss)
    - Total value of transfers since last stock take (at actual xfer prices)
    - All time total value of transfers (at actual xfer prices)
    - Value of held stock at current transfer price
    - Value of held stock at current retail price

- Automated removal of obsolete stock line records (lines with zero units of held stock) from the Store accounts following a successful stock take process
- Historical retention of previous stock take data (not currently exposed on the UI)

## Installation & usage (on Linux systems)

__Below are basic steps to install and run a demonstration of the app on an Linux Ubuntu 20.04 server. They do not provide for a secure installation, such as would be required if the app was publicly available. Steps should be taken to security harden the environment if using in production.__

### Brief installation instructions

- First, clone the repository to your file system.

- Ensure you have access to a current version of PostgreSQL (either locally installed, or remote).

- Ensure gunicorn is installed on your system.

- Create a system user under which to run the application (e.g. `django`). Recursively change ownership of the application directory and all its sub directories to that user, then switch to operate as that user.

- Change into the application's root directory.

- Install a python virtual environment on your system and make that your python source.

- Run `pip3 install -r requirements.txt`.

- Copy `StockManagement/settings.DEFAULT.py` to `StockManagement/settings.py`.

- Edit `StockManagement/settings.py` according to your environment. Be sure to add the URL of your frontend web client to the CORS_ORIGIN_WHITELIST list property.

- Create the PostgreSQL database and user, as defined.

- Create a directory named `secret_key` in the application's root directory and change its ownership to the application user (as created above).

- Change permissions on the `secret_key` directory so only the user running the application can read it, e.g.: `chmod 0700 secret_key`.

- As root (using sudo), create the log directory and file, e.g.:

  - `sudo mkdir -p /var/log/django;`
  - `sudo touch /var/log/django/ssm.log`

- Change ownership of the log directory and its log file to the user running the app, e.g.:

  - `sudo chown -R django /var/log/django/`

- Create a systemd unit file to run the gunicorn service at `/etc/systemd/system/gunicorn.service`, then enable and start start the systemd service (details of how to do this is outwith the scope of this document, but if you need further advice feel free to get in touch).

- Create a systemd unit file to run the django_q service (which manages long running operations, such as 'stock taking') at `/etc/systemd/system/djangoq.service`. Enable and start the systemd service (details of how to do this is outwith the scope of this document, but if you need further advice feel free to get in touch).

- Install a web server (recommended Nginx) to operate as a reverse proxy and create an appropriate configuration file to connect to the unix socket created by gunicorn (as defined above). See the official Nginx and Django documentation for configuration examples.

- Create the database tables, using the commands:

  - `python manage.py makemigrations;`
  - `python manage.py makemigrations stock_control;`
  - `python manage.py makemigrations accounts;`
  - `python manage.py migrate`.

- If running for the first time (i.e. your persistent database folder is empty), define a superuser by issuing the following commands from the application's root directory `python manage.py createsuperuser`.

- In the application's root directory, run `python manage.py collectstatic`, to add the static files to the appropriate directory (ensure the path to the `static` directory has been correctly configured in your web server configuration).



- Now visit the app's administration area in your web browser (e.g. `https://your.domain.tld/admin`).

- If running for the first time, create an `administrators` group and add a new user to it, as follows:

  - Click `add` next to `Groups` in the `Authentication & Authorization` section.
  - Name the new group `administrators`.
  - Under `Available permissions`, scroll to the bottom and select all the `spm_app` permissions, clicking the arrow on the right to add these to the `Chosen permissions` pane (you may hold `shift` to select multiple at once). Once done, click `Save`.
  - Create 2 additional user accounts; one for an application `administrator` (responsible for managing the `warehouse`), the other a regular user (a manager of a client `shop`). Ensure *both* users are assigned the `staff` status.
  - Assign the `administrator` user to the `administrators` group, by: navigating to `Home > Users > username`; scrolling down to the `Permissions` section; selecting `administrators` from the `Available groups` box; and double-clicking it. This moves the group to the `Chosen groups` pane. Then, scroll to the bottom of the page and click `Save`.

- If running for the first time, it's also necessary to initialise the provided frontend client by creating a single stock line from the admin dashboard (this only needs to be done if there are zero stock lines in the database - all subsequent stock items may be added directly from the provided frontend client by users with the `administrators` privilege). To do this:
  
  - Navigate to `Home > Stock_Control > Stock datas` (accessible via the sidebar)
  - Tap the `Add Stock Data` button (top right of the screen)
  - Complete and submit the form.
  
- Click `LOG OUT` (top right)

- Login to the [web client](https://github.com/Aninstance/simple-stock-management-frontend) using the administrator user you created. Begin using Simple Stock Management.

### Update Instructions

- From the application's root directory, run `git pull`. 
- Then, run `pip3 install -r requirements.txt`.
- Then, restart the gunicorn server: `systemctl restart gunicorn.service djangoq.service`.

## Brief UI instructions

Please see the repository for the frontend client, at https://github.com/Aninstance/simple-stock-management-frontend

Note: The above guide is not definitive and is intended for users who know their way around Ubuntu server and Django.

*Users would need to arrange database backups and to secure the application appropriately when used in a production environment.*

## Development Roadmap

- No new features planned at present. To request a change or additional functionality, or to file a bug, please open a github issue and/or contact dan@uplandsdynamic.com.

## Authors

- Dan Bright (Uplands Dynamic), dan@uplandsdynamic.com
