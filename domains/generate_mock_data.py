import os
import json
import random
from datetime import datetime

def generate_data():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cust_dir = os.path.join(base_dir, "storage", "raw", "customers_data")
    sales_dir = os.path.join(base_dir, "storage", "raw", "sales_data")
    
    os.makedirs(cust_dir, exist_ok=True)
    os.makedirs(sales_dir, exist_ok=True)
    
    # 1. Generate Customers (some valid, one invalid)
    customers = [
        {"id": 1001, "name": "Abner Ridigolo", "email": "abner@example.com", "created_at": str(datetime.now()), "status": "active"},
        {"id": 1002, "name": "Maria Silva", "email": "maria@empresa.com.br", "created_at": str(datetime.now()), "status": "active"},
        {"id": 1003, "name": "Carlos Souza", "email": "carlos.souza@gmail.com", "created_at": str(datetime.now()), "status": "inactive"},
        {"id": 1004, "name": "Beatriz Santos", "email": "beatriz@outlook.com", "created_at": str(datetime.now()), "status": "active"},
        # Invalid: Invalid Email
        {"id": 1005, "name": "Erro Email", "email": "email_invalido_sem_arroba", "created_at": str(datetime.now()), "status": "active"},
        # Invalid: Invalid Status
        {"id": 1006, "name": "Erro Status", "email": "error@example.com", "created_at": str(datetime.now()), "status": "suspended"}
    ]
    
    # Write customer files (individual JSONs to simulate event streaming or batch chunks)
    for cust in customers:
        file_path = os.path.join(cust_dir, f"customer_{cust['id']}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cust, f, indent=2)
            
    # 2. Generate Sales (some valid, one invalid)
    sales = [
        {"sale_id": 5001, "customer_id": 1001, "product": "Curso Analytics Engineering", "amount": 299.90, "status": "COMPLETED", "sale_date": str(datetime.now())},
        {"sale_id": 5002, "customer_id": 1002, "product": "Mouse Ergonômico Vertical", "amount": 189.00, "status": "COMPLETED", "sale_date": str(datetime.now())},
        {"sale_id": 5003, "customer_id": 1001, "product": "Teclado Mecânico Keychron", "amount": 549.00, "status": "PENDING", "sale_date": str(datetime.now())},
        {"sale_id": 5004, "customer_id": 1004, "product": "Monitor LG 29 Ultrawide", "amount": 1299.00, "status": "COMPLETED", "sale_date": str(datetime.now())},
        # Invalid: Negative amount
        {"sale_id": 5005, "customer_id": 1003, "product": "Cupom de Desconto Negativo", "amount": -50.00, "status": "COMPLETED", "sale_date": str(datetime.now())},
        # Invalid: Invalid status
        {"sale_id": 5006, "customer_id": 1002, "product": "Fone Sony WH-1000XM4", "amount": 1699.00, "status": "SHIPPED", "sale_date": str(datetime.now())}
    ]
    
    # Write sales files
    for sale in sales:
        file_path = os.path.join(sales_dir, f"sale_{sale['sale_id']}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(sale, f, indent=2)
            
    print(f"Mock data generated successfully: {len(customers)} customers, {len(sales)} sales.")

if __name__ == "__main__":
    generate_data()
