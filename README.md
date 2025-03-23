# Simpler Stock Management (Beta)

Simpler Stock Management is a web application designed to help manage warehouse and shop stock efficiently. The application provides features for searching, sorting, updating, and transferring stock items between the warehouse and shops. Data is stored in a local SQLite3 database.

Note, this is an early beta release. It is intended for testing only, and is not yet suitable for production deployment.

The earlier version (pre-V5) 'Simple Stock Management' app has been entirely rewritten from scratch. Little-used functionality has been removed and the code is now simpler and [more maintainable](#what-changed). The earlier legacy version is now unmaintained, however the code may still be accessed in the [legacy_v4 branch](https://github.com/consciousuniverse/simple-stock-management/tree/legacy_v4).

## Security

This app has not been audited for security and probably does contain vulnerabilities that could expose data contained on the host system to unauthorized manipulation or disclosure. 
Deploy at your own risk and on a server that has *NO ACCESS* to your primary systems, or indeed any system where compromise could reveal personally identifiable information or other sensitive data. For example, a standalone VPS machine. Please also remember to remotely *BACK UP* the sqlite database.

In addition, regular updates of Python dependencies to the latest versions is necessary, to ensure patching of any discovered vulnerabilities (this may be achieved through your python package manager, such as pip or pipenv).

## Features

### User Authentication
- **Login/Logout**: Users can log in and log out of the application.
- **User Status**: Displays the logged-in user's status.

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

## Screenshots

### Warehouse manager's view
![image](https://github.com/user-attachments/assets/54ddbe64-7278-4aa7-a0e4-8fced6c42bad)

### Shop view
![image](https://github.com/user-attachments/assets/9b18c4df-f92c-435d-a216-cdd492785c10)

## What changed?

The backend is still Django Rest Framework, while the frontend is now plain old jQuery, rather than relying on ReactJS with all its dependencies. The frontend is now integrated into the Django app, as opposed to the previous standalone frontend UI.

## License

Simpler Stock Management is licensed under the GPLv3. See the [LICENSE](LICENSE) file for more details.

## Author

Dan Bright - [GitHub](https://github.com/consciousuniverse), github@bright.contact
