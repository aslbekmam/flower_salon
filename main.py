import sys
import pymysql
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox,
                             QTabWidget, QTableWidget, QTableWidgetItem, QDateEdit, QTimeEdit,
                             QSpinBox, QFormLayout, QDialog, QHeaderView, QGroupBox)
from PyQt5.QtCore import Qt, QDate, QTime, QSettings


class Database:
    def __init__(self):
        self.connection = None

    def connect(self, host='localhost', user='root', password='', database='chetochny'):
        try:
            self.connection = pymysql.connect(
                host=host,
                user=user,
                password=password,
                database=database,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            return True
        except Exception as e:
            return False

    def disconnect(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def execute_query(self, query, params=None):
        if not self.connection:
            return None
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                if query.strip().upper().startswith('SELECT'):
                    result = cursor.fetchall()
                    return result
                else:
                    self.connection.commit()
                    return cursor.lastrowid
        except Exception as e:
            self.connection.rollback()
            raise e

    def get_customers(self):
        return self.execute_query("SELECT * FROM customers ORDER BY full_name")

    def get_employees(self):
        return self.execute_query("SELECT * FROM employees ORDER BY full_name")

    def get_products(self):
        return self.execute_query("""
            SELECT p.*, c.category_name 
            FROM products p 
            JOIN product_categories c ON p.category_id = c.category_id 
            ORDER BY p.product_name
        """)

    def get_orders(self, status_filter=None, date_filter=None):
        query = """
            SELECT o.*, c.full_name as customer_name, e.full_name as employee_name
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            JOIN employees e ON o.employee_responsible_id = e.employee_id
        """
        params = []

        if status_filter and status_filter != "Все":
            query += " WHERE o.status = %s"
            params.append(status_filter)

        if date_filter:
            if params:
                query += " AND DATE(o.order_date) = %s"
            else:
                query += " WHERE DATE(o.order_date) = %s"
            params.append(date_filter)

        query += " ORDER BY o.order_date DESC"

        return self.execute_query(query, params) if params else self.execute_query(query)

    def get_order_items(self, order_id):
        return self.execute_query("""
            SELECT oi.*, p.product_name
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            WHERE oi.order_id = %s
        """, (order_id,))

    def create_order(self, customer_id, employee_id, delivery_date, delivery_time_from,
                     delivery_time_to, delivery_address, payment_method, items):
        order_query = """
            INSERT INTO orders (customer_id, employee_responsible_id, order_date, 
                              delivery_date, delivery_time_from, delivery_time_to, 
                              delivery_address, status, total_amount, payment_method)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s, 'В обработке', %s, %s)
        """

        total_amount = sum(item['quantity'] * item['price'] for item in items)

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(order_query, (customer_id, employee_id, delivery_date,
                                             delivery_time_from, delivery_time_to,
                                             delivery_address, total_amount, payment_method))
                order_id = cursor.lastrowid

                for item in items:
                    item_query = """
                        INSERT INTO order_items (order_id, product_id, quantity, price_per_unit)
                        VALUES (%s, %s, %s, %s)
                    """
                    cursor.execute(item_query, (order_id, item['product_id'],
                                                item['quantity'], item['price']))

                self.connection.commit()
                return order_id
        except Exception as e:
            self.connection.rollback()
            raise e

    def update_order_status(self, order_id, status):
        return self.execute_query(
            "UPDATE orders SET status = %s WHERE order_id = %s",
            (status, order_id)
        )

    def authenticate_user(self, email, password, user_type):
        if user_type == "admin":
            query = "SELECT * FROM employees WHERE email = %s AND password = %s"
        else:
            query = "SELECT * FROM customers WHERE email = %s AND password = %s"

        result = self.execute_query(query, (email, password))
        return result[0] if result else None


class OrderDialog(QDialog):
    def __init__(self, db, parent=None, order_id=None):
        super().__init__(parent)
        self.db = db
        self.order_id = order_id
        self.order_items = []
        self.initUI()

        if order_id:
            self.load_order_data()

    def initUI(self):
        self.setWindowTitle('Новый заказ' if not self.order_id else 'Редактирование заказа')
        self.setFixedSize(800, 600)

        layout = QVBoxLayout()

        form_layout = QFormLayout()

        self.customer_combo = QComboBox()
        customers = self.db.get_customers()
        for customer in customers:
            self.customer_combo.addItem(customer['full_name'], customer['customer_id'])
        form_layout.addRow('Клиент:', self.customer_combo)

        self.employee_combo = QComboBox()
        employees = self.db.get_employees()
        for employee in employees:
            self.employee_combo.addItem(employee['full_name'], employee['employee_id'])
        form_layout.addRow('Сотрудник:', self.employee_combo)

        self.delivery_date = QDateEdit()
        self.delivery_date.setDate(QDate.currentDate().addDays(1))
        self.delivery_date.setCalendarPopup(True)
        form_layout.addRow('Дата доставки:', self.delivery_date)

        self.delivery_time_from = QTimeEdit()
        self.delivery_time_from.setTime(QTime(12, 0))
        form_layout.addRow('Время с:', self.delivery_time_from)

        self.delivery_time_to = QTimeEdit()
        self.delivery_time_to.setTime(QTime(14, 0))
        form_layout.addRow('Время до:', self.delivery_time_to)

        self.delivery_address = QLineEdit()
        self.delivery_address.setPlaceholderText('Введите адрес доставки')
        form_layout.addRow('Адрес доставки:', self.delivery_address)

        self.payment_method = QComboBox()
        self.payment_method.addItems(['Карта', 'Наличные', 'Онлайн'])
        form_layout.addRow('Способ оплаты:', self.payment_method)

        if self.order_id:
            self.status_combo = QComboBox()
            self.status_combo.addItems(['В обработке', 'Завершен', 'Отменен'])
            form_layout.addRow('Статус:', self.status_combo)

        layout.addLayout(form_layout)

        products_label = QLabel('Товары в заказе:')
        layout.addWidget(products_label)

        self.products_table = QTableWidget()
        self.products_table.setColumnCount(5)
        self.products_table.setHorizontalHeaderLabels(['Товар', 'Цена', 'Кол-во', 'Сумма', 'Действия'])
        self.products_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.products_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.products_table)

        add_product_layout = QHBoxLayout()

        self.product_combo = QComboBox()
        products = self.db.get_products()
        for product in products:
            self.product_combo.addItem(f"{product['product_name']} - {product['price']:.2f}", product)
        add_product_layout.addWidget(QLabel('Товар:'))
        add_product_layout.addWidget(self.product_combo)

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setMinimum(1)
        self.quantity_spin.setMaximum(100)
        self.quantity_spin.setValue(1)
        add_product_layout.addWidget(QLabel('Кол-во:'))
        add_product_layout.addWidget(self.quantity_spin)

        add_button = QPushButton('Добавить товар')
        add_button.clicked.connect(self.add_product)
        add_product_layout.addWidget(add_button)

        add_product_layout.addStretch()
        layout.addLayout(add_product_layout)

        total_layout = QHBoxLayout()
        total_layout.addStretch()

        self.total_label = QLabel('Итого: 0.00 руб.')
        self.total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        total_layout.addWidget(self.total_label)

        layout.addLayout(total_layout)

        button_layout = QHBoxLayout()

        save_button = QPushButton('Сохранить')
        save_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 10px 20px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        save_button.clicked.connect(self.save_order)
        button_layout.addWidget(save_button)

        cancel_button = QPushButton('Отмена')
        cancel_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 10px 20px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

        self.load_products_table()

    def load_products_table(self):
        self.products_table.setRowCount(len(self.order_items))
        for row, item in enumerate(self.order_items):
            self.products_table.setItem(row, 0, QTableWidgetItem(item['product_name']))
            self.products_table.setItem(row, 1, QTableWidgetItem(f"{item['price']:.2f}"))
            self.products_table.setItem(row, 2, QTableWidgetItem(str(item['quantity'])))
            self.products_table.setItem(row, 3, QTableWidgetItem(f"{item['quantity'] * item['price']:.2f}"))

            remove_button = QPushButton('Удалить')
            remove_button.clicked.connect(lambda checked, r=row: self.remove_product(r))
            self.products_table.setCellWidget(row, 4, remove_button)

        self.update_total()

    def add_product(self):
        product = self.product_combo.currentData()
        quantity = self.quantity_spin.value()

        if product:
            item = {
                'product_id': product['product_id'],
                'product_name': product['product_name'],
                'price': float(product['price']),
                'quantity': quantity
            }
            self.order_items.append(item)
            self.load_products_table()

    def remove_product(self, row):
        if row < len(self.order_items):
            del self.order_items[row]
            self.load_products_table()

    def update_total(self):
        total = sum(item['quantity'] * item['price'] for item in self.order_items)
        self.total_label.setText(f'Итого: {total:.2f} руб.')

    def load_order_data(self):
        orders = self.db.get_orders()
        order = next((o for o in orders if o['order_id'] == self.order_id), None)

        if order:
            customer_index = self.customer_combo.findData(order['customer_id'])
            if customer_index >= 0:
                self.customer_combo.setCurrentIndex(customer_index)

            employee_index = self.employee_combo.findData(order['employee_responsible_id'])
            if employee_index >= 0:
                self.employee_combo.setCurrentIndex(employee_index)

            self.delivery_date.setDate(QDate.fromString(str(order['delivery_date']), 'yyyy-MM-dd'))

            if order['delivery_time_from']:
                self.delivery_time_from.setTime(QTime.fromString(str(order['delivery_time_from']), 'hh:mm:ss'))

            if order['delivery_time_to']:
                self.delivery_time_to.setTime(QTime.fromString(str(order['delivery_time_to']), 'hh:mm:ss'))

            self.delivery_address.setText(order['delivery_address'])
            self.payment_method.setCurrentText(order['payment_method'])
            self.status_combo.setCurrentText(order['status'])

            order_items = self.db.get_order_items(self.order_id)
            for item in order_items:
                self.order_items.append({
                    'product_id': item['product_id'],
                    'product_name': item['product_name'],
                    'price': float(item['price_per_unit']),
                    'quantity': item['quantity']
                })

            self.load_products_table()

    def save_order(self):
        if not self.order_items:
            QMessageBox.warning(self, 'Ошибка', 'Добавьте хотя бы один товар в заказ')
            return

        customer_id = self.customer_combo.currentData()
        employee_id = self.employee_combo.currentData()
        delivery_date = self.delivery_date.date().toString('yyyy-MM-dd')
        delivery_time_from = self.delivery_time_from.time().toString('hh:mm:ss')
        delivery_time_to = self.delivery_time_to.time().toString('hh:mm:ss')
        delivery_address = self.delivery_address.text().strip()
        payment_method = self.payment_method.currentText()

        if not delivery_address:
            QMessageBox.warning(self, 'Ошибка', 'Введите адрес доставки')
            return

        try:
            if self.order_id:
                self.db.create_order(customer_id, employee_id, delivery_date,
                                     delivery_time_from, delivery_time_to,
                                     delivery_address, payment_method, self.order_items)
                QMessageBox.information(self, 'Успех', 'Заказ успешно обновлен')
            else:
                order_id = self.db.create_order(customer_id, employee_id, delivery_date,
                                                delivery_time_from, delivery_time_to,
                                                delivery_address, payment_method, self.order_items)
                QMessageBox.information(self, 'Успех', f'Заказ #{order_id} успешно создан')

            if self.order_id and hasattr(self, 'status_combo'):
                self.db.update_order_status(self.order_id, self.status_combo.currentText())

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, 'Ошибка', f'Ошибка при сохранении заказа: {str(e)}')


class OrderDetailsDialog(QDialog):
    def __init__(self, order_id, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.order_id = order_id
        self.initUI()
        self.load_order_data()

    def initUI(self):
        self.setWindowTitle(f'Детали заказа #{self.order_id}')
        self.setFixedSize(700, 500)

        layout = QVBoxLayout()

        self.info_layout = QFormLayout()
        layout.addLayout(self.info_layout)

        items_label = QLabel('Товары в заказе:')
        items_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 20px;")
        layout.addWidget(items_label)

        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels(['Товар', 'Цена', 'Количество', 'Сумма'])
        self.items_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.items_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.items_table)

        total_layout = QHBoxLayout()
        total_layout.addStretch()

        self.total_label = QLabel('Итого: 0.00 руб.')
        self.total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        total_layout.addWidget(self.total_label)

        layout.addLayout(total_layout)

        if hasattr(parent, 'user_type') and parent.user_type == 'admin':
            status_layout = QHBoxLayout()
            status_layout.addWidget(QLabel('Статус:'))

            self.status_combo = QComboBox()
            self.status_combo.addItems(['В обработке', 'Завершен', 'Отменен'])
            status_layout.addWidget(self.status_combo)

            update_status_button = QPushButton('Обновить статус')
            update_status_button.clicked.connect(self.update_status)
            status_layout.addWidget(update_status_button)

            status_layout.addStretch()
            layout.addLayout(status_layout)

        button_layout = QHBoxLayout()

        close_button = QPushButton('Закрыть')
        close_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 8px 15px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def load_order_data(self):
        orders = self.db.get_orders()
        order = next((o for o in orders if o['order_id'] == self.order_id), None)

        if order:
            self.info_layout.addRow('ID заказа:', QLabel(str(order['order_id'])))
            self.info_layout.addRow('Клиент:', QLabel(order['customer_name']))
            self.info_layout.addRow('Сотрудник:', QLabel(order['employee_name']))
            self.info_layout.addRow('Дата заказа:', QLabel(str(order['order_date'])))
            self.info_layout.addRow('Дата доставки:', QLabel(str(order['delivery_date'])))
            self.info_layout.addRow('Время доставки:',
                                    QLabel(f"{order['delivery_time_from']} - {order['delivery_time_to']}"))
            self.info_layout.addRow('Адрес доставки:', QLabel(order['delivery_address']))
            self.info_layout.addRow('Статус:', QLabel(order['status']))
            self.info_layout.addRow('Способ оплаты:', QLabel(order['payment_method']))

            if hasattr(self, 'status_combo'):
                self.status_combo.setCurrentText(order['status'])

            order_items = self.db.get_order_items(self.order_id)
            self.items_table.setRowCount(len(order_items))

            total = 0
            for row, item in enumerate(order_items):
                self.items_table.setItem(row, 0, QTableWidgetItem(item['product_name']))
                self.items_table.setItem(row, 1, QTableWidgetItem(f"{item['price_per_unit']:.2f}"))
                self.items_table.setItem(row, 2, QTableWidgetItem(str(item['quantity'])))
                item_total = item['quantity'] * item['price_per_unit']
                self.items_table.setItem(row, 3, QTableWidgetItem(f"{item_total:.2f}"))
                total += item_total

            self.total_label.setText(f'Итого: {total:.2f} руб.')

    def update_status(self):
        new_status = self.status_combo.currentText()
        try:
            self.db.update_order_status(self.order_id, new_status)
            QMessageBox.information(self, 'Успех', 'Статус заказа обновлен')
            self.load_order_data()
        except Exception as e:
            QMessageBox.critical(self, 'Ошибка', f'Ошибка при обновлении статуса: {str(e)}')


class MainWindow(QMainWindow):
    def __init__(self, user, user_type, db):
        super().__init__()
        self.user = user
        self.user_type = user_type
        self.db = db
        self.initUI()

    def initUI(self):
        self.setWindowTitle(f'Цветочный магазин - {self.user["full_name"]}')
        self.setGeometry(100, 100, 1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()

        header_layout = QHBoxLayout()
        user_label = QLabel(f'Пользователь: {self.user["full_name"]}')
        user_label.setStyleSheet("font-weight: bold; padding: 5px;")
        header_layout.addWidget(user_label)

        header_layout.addStretch()

        layout.addLayout(header_layout)

        self.tabs = QTabWidget()

        if self.user_type == 'admin':
            self.setup_admin_tabs()
        else:
            self.setup_customer_tabs()

        layout.addWidget(self.tabs)
        central_widget.setLayout(layout)

    def setup_admin_tabs(self):
        orders_tab = QWidget()
        self.setup_orders_tab(orders_tab)
        self.tabs.addTab(orders_tab, 'Заказы')

        products_tab = QWidget()
        self.setup_products_tab(products_tab)
        self.tabs.addTab(products_tab, 'Товары')

        customers_tab = QWidget()
        self.setup_customers_tab(customers_tab)
        self.tabs.addTab(customers_tab, 'Клиенты')

    def setup_customer_tabs(self):
        booking_tab = QWidget()
        self.setup_booking_tab(booking_tab)
        self.tabs.addTab(booking_tab, 'Создать заказ')

        history_tab = QWidget()
        self.setup_history_tab(history_tab)
        self.tabs.addTab(history_tab, 'История заказов')

        profile_tab = QWidget()
        self.setup_profile_tab(profile_tab)
        self.tabs.addTab(profile_tab, 'Профиль')

    def setup_orders_tab(self, tab):
        layout = QVBoxLayout()

        filter_group = QGroupBox("Фильтры")
        filter_layout = QHBoxLayout()

        self.status_filter = QComboBox()
        self.status_filter.addItems(['Все', 'В обработке', 'Завершен', 'Отменен'])
        filter_layout.addWidget(QLabel('Статус:'))
        filter_layout.addWidget(self.status_filter)

        self.date_filter = QDateEdit()
        self.date_filter.setDate(QDate.currentDate())
        self.date_filter.setCalendarPopup(True)
        filter_layout.addWidget(QLabel('Дата:'))
        filter_layout.addWidget(self.date_filter)

        filter_button = QPushButton('Фильтровать')
        filter_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 5px 15px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        filter_button.clicked.connect(self.filter_orders)
        filter_layout.addWidget(filter_button)

        show_all_button = QPushButton('Показать все')
        show_all_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 5px 15px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        show_all_button.clicked.connect(self.show_all_orders)
        filter_layout.addWidget(show_all_button)

        filter_layout.addStretch()
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        self.orders_table = QTableWidget()
        self.orders_table.setColumnCount(9)
        self.orders_table.setHorizontalHeaderLabels([
            'ID', 'Клиент', 'Сотрудник', 'Дата заказа', 'Дата доставки',
            'Адрес', 'Статус', 'Сумма', 'Оплата'
        ])
        self.orders_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.orders_table)

        button_layout = QHBoxLayout()

        new_order_button = QPushButton('Новый заказ')
        new_order_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 8px 15px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        new_order_button.clicked.connect(self.create_new_order)
        button_layout.addWidget(new_order_button)

        edit_order_button = QPushButton('Редактировать')
        edit_order_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 8px 15px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        edit_order_button.clicked.connect(self.edit_order)
        button_layout.addWidget(edit_order_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        tab.setLayout(layout)
        self.load_orders()

    def setup_products_tab(self, tab):
        layout = QVBoxLayout()

        self.products_table = QTableWidget()
        self.products_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.products_table.setColumnCount(6)
        self.products_table.setHorizontalHeaderLabels([
            'ID', 'Категория', 'Название', 'Описание', 'Цена', 'Ед. изм.'
        ])
        self.products_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.products_table)

        tab.setLayout(layout)
        self.load_products()

    def setup_customers_tab(self, tab):
        layout = QVBoxLayout()

        self.customers_table = QTableWidget()
        self.customers_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.customers_table.setColumnCount(7)
        self.customers_table.setHorizontalHeaderLabels([
            'ID', 'ФИО', 'День рождения', 'Телефон', 'Email', 'Дата рег.', 'Источник'
        ])
        self.customers_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.customers_table)

        tab.setLayout(layout)
        self.load_customers()

    def setup_booking_tab(self, tab):
        layout = QVBoxLayout()

        booking_label = QLabel('Создание заказа')
        booking_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 20px;")
        layout.addWidget(booking_label)

        # Основная информация
        info_group = QGroupBox("Информация о доставке")
        info_layout = QFormLayout()

        self.delivery_address = QLineEdit()
        self.delivery_address.setPlaceholderText('Введите адрес доставки')
        info_layout.addRow('Адрес:', self.delivery_address)

        self.delivery_date = QDateEdit()
        self.delivery_date.setDate(QDate.currentDate().addDays(1))
        self.delivery_date.setCalendarPopup(True)
        info_layout.addRow('Дата:', self.delivery_date)

        self.delivery_time = QComboBox()
        self.delivery_time.addItems(['09:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00',
                                     '13:00-14:00', '14:00-15:00', '15:00-16:00', '16:00-17:00', '17:00-18:00'])
        info_layout.addRow('Время:', self.delivery_time)

        self.payment_method = QComboBox()
        self.payment_method.addItems(['Карта', 'Наличные', 'Онлайн'])
        info_layout.addRow('Оплата:', self.payment_method)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Товары
        products_group = QGroupBox("Товары")
        products_layout = QVBoxLayout()

        add_product_layout = QHBoxLayout()

        self.product_combo = QComboBox()
        add_product_layout.addWidget(QLabel('Товар:'))
        add_product_layout.addWidget(self.product_combo)

        self.quantity_spin = QSpinBox()
        self.quantity_spin.setMinimum(1)
        self.quantity_spin.setMaximum(100)
        self.quantity_spin.setValue(1)
        add_product_layout.addWidget(QLabel('Кол-во:'))
        add_product_layout.addWidget(self.quantity_spin)

        add_product_button = QPushButton('Добавить')
        add_product_button.clicked.connect(self.add_product_to_booking)
        add_product_layout.addWidget(add_product_button)

        add_product_layout.addStretch()
        products_layout.addLayout(add_product_layout)

        self.booking_products_table = QTableWidget()
        self.booking_products_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.booking_products_table.setColumnCount(4)
        self.booking_products_table.setHorizontalHeaderLabels(['Товар', 'Цена', 'Кол-во', 'Сумма'])
        self.booking_products_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        products_layout.addWidget(self.booking_products_table)

        products_group.setLayout(products_layout)
        layout.addWidget(products_group)

        # Итог
        total_layout = QHBoxLayout()
        total_layout.addStretch()

        self.total_label = QLabel('Итого: 0.00 руб.')
        self.total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        total_layout.addWidget(self.total_label)

        layout.addLayout(total_layout)

        # Кнопка
        submit_layout = QHBoxLayout()
        submit_layout.addStretch()

        submit_booking_button = QPushButton('Оформить заказ')
        submit_booking_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 10px 20px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        submit_booking_button.clicked.connect(self.submit_booking)
        submit_layout.addWidget(submit_booking_button)

        layout.addLayout(submit_layout)
        tab.setLayout(layout)
        self.load_booking_products()

    def load_booking_products(self):
        if not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        products = self.db.get_products()

        self.product_combo.clear()
        for product in products:
            self.product_combo.addItem(f"{product['product_name']} - {product['price']:.2f}", product)

        self.booking_items = []
        self.update_booking_table()

    def add_product_to_booking(self):
        product = self.product_combo.currentData()
        quantity = self.quantity_spin.value()

        if product:
            item = {
                'product_id': product['product_id'],
                'product_name': product['product_name'],
                'price': float(product['price']),
                'quantity': quantity
            }
            self.booking_items.append(item)
            self.update_booking_table()

    def update_booking_table(self):
        if hasattr(self, 'booking_products_table'):
            self.booking_products_table.setRowCount(len(self.booking_items))
            for row, item in enumerate(self.booking_items):
                self.booking_products_table.setItem(row, 0, QTableWidgetItem(item['product_name']))
                self.booking_products_table.setItem(row, 1, QTableWidgetItem(f"{item['price']:.2f}"))
                self.booking_products_table.setItem(row, 2, QTableWidgetItem(str(item['quantity'])))
                self.booking_products_table.setItem(row, 3, QTableWidgetItem(f"{item['quantity'] * item['price']:.2f}"))

            total = sum(item['quantity'] * item['price'] for item in self.booking_items)
            self.total_label.setText(f'Итого: {total:.2f} руб.')

    def remove_booking_item(self, row):
        if row < len(self.booking_items):
            del self.booking_items[row]
            self.update_booking_table()

    def submit_booking(self):
        if not self.booking_items:
            QMessageBox.warning(self, 'Ошибка', 'Добавьте хотя бы один товар в заказ')
            return

        delivery_address = self.delivery_address.text().strip()
        if not delivery_address:
            QMessageBox.warning(self, 'Ошибка', 'Введите адрес доставки')
            return

        try:
            if not self.db.connection:
                self.db.connect('localhost', 'root', '', 'chetochny')

            customer_id = self.user['customer_id']
            employee_id = 1  # Первый сотрудник по умолчанию
            delivery_date = self.delivery_date.date().toString('yyyy-MM-dd')

            # Разбираем время из формата "09:00-10:00"
            time_range = self.delivery_time.currentText()
            time_parts = time_range.split('-')
            delivery_time_from = time_parts[0] + ':00'
            delivery_time_to = time_parts[1] + ':00'

            payment_method = self.payment_method.currentText()

            order_id = self.db.create_order(customer_id, employee_id, delivery_date,
                                            delivery_time_from, delivery_time_to,
                                            delivery_address, payment_method, self.booking_items)

            QMessageBox.information(self, 'Успех', f'Заказ #{order_id} успешно создан!')

            # Очистка формы
            self.booking_items = []
            self.update_booking_table()
            self.delivery_address.clear()
            self.delivery_date.setDate(QDate.currentDate().addDays(1))

        except Exception as e:
            QMessageBox.critical(self, 'Ошибка', f'Ошибка при создании заказа: {str(e)}')

    def setup_history_tab(self, tab):
        layout = QVBoxLayout()

        self.history_table = QTableWidget()
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels([
            'ID', 'Дата заказа', 'Дата доставки', 'Адрес', 'Статус', 'Сумма', 'Оплата'
        ])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.history_table)

        tab.setLayout(layout)
        self.load_order_history()

    def setup_profile_tab(self, tab):
        layout = QVBoxLayout()

        profile_group = QGroupBox("Личная информация")
        profile_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        profile_layout = QFormLayout()

        full_name_label = QLabel(self.user['full_name'])
        full_name_label.setStyleSheet("font-size: 14px; padding: 5px;")
        profile_layout.addRow('ФИО:', full_name_label)

        if 'birthday' in self.user:
            birthday_label = QLabel(str(self.user['birthday']) if self.user['birthday'] else 'Не указано')
            birthday_label.setStyleSheet("font-size: 14px; padding: 5px;")
            profile_layout.addRow('Дата рождения:', birthday_label)

        if 'phone' in self.user:
            phone_label = QLabel(self.user['phone'])
            phone_label.setStyleSheet("font-size: 14px; padding: 5px;")
            profile_layout.addRow('Телефон:', phone_label)

        email_label = QLabel(self.user['email'])
        email_label.setStyleSheet("font-size: 14px; padding: 5px;")
        profile_layout.addRow('Email:', email_label)

        if 'registration_date' in self.user:
            registration_label = QLabel(
                str(self.user['registration_date']) if self.user['registration_date'] else 'Не указано')
            registration_label.setStyleSheet("font-size: 14px; padding: 5px;")
            profile_layout.addRow('Дата регистрации:', registration_label)

        if 'source_c' in self.user:
            source_label = QLabel(self.user['source_c'] if self.user['source_c'] else 'Не указано')
            source_label.setStyleSheet("font-size: 14px; padding: 5px;")
            profile_layout.addRow('Источник:', source_label)

        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)

        stats_group = QGroupBox("Статистика")
        stats_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        stats_layout = QVBoxLayout()

        orders_count_label = QLabel('Всего заказов: 3')
        orders_count_label.setStyleSheet("font-size: 14px; padding: 5px;")
        stats_layout.addWidget(orders_count_label)

        total_spent_label = QLabel('Общая сумма: 4,150.00 руб.')
        total_spent_label.setStyleSheet("font-size: 14px; padding: 5px;")
        stats_layout.addWidget(total_spent_label)

        last_order_label = QLabel('Последний заказ: 04.03.2024')
        last_order_label.setStyleSheet("font-size: 14px; padding: 5px;")
        stats_layout.addWidget(last_order_label)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        layout.addStretch()
        tab.setLayout(layout)

    def load_orders(self):
        if self.user_type == 'admin' and not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        orders = self.db.get_orders()
        self.populate_orders_table(orders)

    def populate_orders_table(self, orders):
        self.orders_table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            self.orders_table.setItem(row, 0, QTableWidgetItem(str(order['order_id'])))
            self.orders_table.setItem(row, 1, QTableWidgetItem(order['customer_name']))
            self.orders_table.setItem(row, 2, QTableWidgetItem(order['employee_name']))
            self.orders_table.setItem(row, 3, QTableWidgetItem(str(order['order_date'])))
            self.orders_table.setItem(row, 4, QTableWidgetItem(str(order['delivery_date'])))
            self.orders_table.setItem(row, 5, QTableWidgetItem(order['delivery_address']))
            self.orders_table.setItem(row, 6, QTableWidgetItem(order['status']))
            self.orders_table.setItem(row, 7, QTableWidgetItem(f"{order['total_amount']:.2f}"))
            self.orders_table.setItem(row, 8, QTableWidgetItem(order['payment_method']))

    def load_products(self):
        if self.user_type == 'admin' and not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        if hasattr(self, 'products_table'):
            products = self.db.get_products()
            self.products_table.setRowCount(len(products))
            for row, product in enumerate(products):
                self.products_table.setItem(row, 0, QTableWidgetItem(str(product['product_id'])))
                self.products_table.setItem(row, 1, QTableWidgetItem(product['category_name']))
                self.products_table.setItem(row, 2, QTableWidgetItem(product['product_name']))
                self.products_table.setItem(row, 3, QTableWidgetItem(product['description'] or ''))
                self.products_table.setItem(row, 4, QTableWidgetItem(f"{product['price']:.2f}"))
                self.products_table.setItem(row, 5, QTableWidgetItem(product['unit']))

    def load_customers(self):
        if self.user_type == 'admin' and not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        if hasattr(self, 'customers_table'):
            customers = self.db.get_customers()
            self.customers_table.setRowCount(len(customers))
            for row, customer in enumerate(customers):
                self.customers_table.setItem(row, 0, QTableWidgetItem(str(customer['customer_id'])))
                self.customers_table.setItem(row, 1, QTableWidgetItem(customer['full_name']))
                self.customers_table.setItem(row, 2, QTableWidgetItem(
                    str(customer['birthday']) if customer['birthday'] else ''))
                self.customers_table.setItem(row, 3, QTableWidgetItem(customer['phone']))
                self.customers_table.setItem(row, 4, QTableWidgetItem(customer['email']))
                self.customers_table.setItem(row, 5, QTableWidgetItem(
                    str(customer['registration_date']) if customer['registration_date'] else ''))
                self.customers_table.setItem(row, 6, QTableWidgetItem(customer['source_c'] or ''))

    def load_order_history(self):
        if not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        if hasattr(self, 'history_table'):
            orders = self.db.get_orders()
            customer_orders = [order for order in orders if order['customer_id'] == self.user['customer_id']]

            self.history_table.setRowCount(len(customer_orders))
            for row, order in enumerate(customer_orders):
                self.history_table.setItem(row, 0, QTableWidgetItem(str(order['order_id'])))
                self.history_table.setItem(row, 1, QTableWidgetItem(str(order['order_date'])))
                self.history_table.setItem(row, 2, QTableWidgetItem(str(order['delivery_date'])))
                self.history_table.setItem(row, 3, QTableWidgetItem(order['delivery_address']))
                self.history_table.setItem(row, 4, QTableWidgetItem(order['status']))
                self.history_table.setItem(row, 5, QTableWidgetItem(f"{order['total_amount']:.2f}"))
                self.history_table.setItem(row, 6, QTableWidgetItem(order['payment_method']))

    def filter_orders(self):
        if self.user_type == 'admin' and not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        status = self.status_filter.currentText()
        date = self.date_filter.date().toString('yyyy-MM-dd')
        orders = self.db.get_orders(status, date)
        self.populate_orders_table(orders)

    def show_all_orders(self):
        self.status_filter.setCurrentIndex(0)
        self.load_orders()

    def create_new_order(self):
        if self.user_type == 'admin' and not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        dialog = OrderDialog(self.db, self)
        if dialog.exec_() == QDialog.Accepted:
            self.load_orders()

    def edit_order(self):
        if self.user_type == 'admin' and not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        current_row = self.orders_table.currentRow()
        if current_row >= 0:
            order_id = int(self.orders_table.item(current_row, 0).text())
            dialog = OrderDialog(self.db, self, order_id)
            if dialog.exec_() == QDialog.Accepted:
                self.load_orders()
        else:
            QMessageBox.warning(self, 'Внимание', 'Выберите заказ для редактирования')

    def show_order_details(self, order_id):
        if self.user_type == 'admin' and not self.db.connection:
            self.db.connect('localhost', 'root', '', 'chetochny')
        dialog = OrderDetailsDialog(order_id, self.db, self)
        dialog.exec_()


class LoginWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.main_window = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Цветочный магазин')
        self.setFixedSize(400, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        title_label = QLabel('Вход в систему')
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 20px;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        email_label = QLabel('Логин:')
        layout.addWidget(email_label)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText('Введите логин')
        self.email_input.setStyleSheet("padding: 5px; margin-bottom: 10px; border: 1px solid #ccc;")
        layout.addWidget(self.email_input)

        password_label = QLabel('Пароль:')
        layout.addWidget(password_label)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText('Введите пароль')
        self.password_input.setStyleSheet("padding: 5px; margin-bottom: 20px; border: 1px solid #ccc;")
        layout.addWidget(self.password_input)

        login_button = QPushButton('Войти')
        login_button.setStyleSheet("""
            QPushButton {
                background-color: white;
                color: black;
                padding: 10px;
                font-size: 14px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
            }
        """)
        login_button.clicked.connect(self.login)
        layout.addWidget(login_button)

        central_widget.setLayout(layout)

        self.email_input.returnPressed.connect(self.login)
        self.password_input.returnPressed.connect(self.login)

    def login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()

        if not email or not password:
            QMessageBox.warning(self, 'Ошибка', 'Заполните все поля')
            return

        if email == 'admin' and password == 'admin':
            user = {
                'employee_id': 1,
                'full_name': 'Администратор',
                'email': 'admin',
                'position': 'Администратор'
            }
            try:
                self.main_window = MainWindow(user, 'admin', self.db)
                self.main_window.show()
                self.hide()
            except Exception as e:
                QMessageBox.critical(self, 'Ошибка', f'Ошибка при запуске главного окна: {str(e)}')
            return

        if email == 'client' and password == 'client':
            user = {
                'customer_id': 1,
                'full_name': 'Иванов Иван Иванович',
                'email': 'client',
                'phone': '+7 (915) 000-11-22',
                'birthday': '1985-05-15',
                'registration_date': '2023-01-12',
                'source_c': 'Реклама'
            }
            try:
                self.main_window = MainWindow(user, 'customer', self.db)
                self.main_window.show()
                self.hide()
            except Exception as e:
                QMessageBox.critical(self, 'Ошибка', f'Ошибка при запуске главного окна: {str(e)}')
            return

        if email == 'client2' and password == 'client2':
            user = {
                'customer_id': 2,
                'full_name': 'Сидорова Анна Петровна',
                'email': 'client2',
                'phone': '+7 (917) 000-78-90',
                'birthday': '1980-11-30',
                'registration_date': '2024-02-15',
                'source_c': 'Рекомендация'
            }
            try:
                self.main_window = MainWindow(user, 'customer', self.db)
                self.main_window.show()
                self.hide()
            except Exception as e:
                QMessageBox.critical(self, 'Ошибка', f'Ошибка при запуске главного окна: {str(e)}')
            return

        if not self.db.connect('localhost', 'root', '', 'chetochny'):
            QMessageBox.warning(self, 'Ошибка', 'Не удалось подключиться к базе данных')
            return

        user = self.db.authenticate_user(email, password, 'customer')

        if user:
            self.main_window = MainWindow(user, 'customer', self.db)
            self.main_window.show()
            self.hide()
        else:
            QMessageBox.warning(self, 'Ошибка', 'Неверный логин или пароль')


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    login_window = LoginWindow()
    login_window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
