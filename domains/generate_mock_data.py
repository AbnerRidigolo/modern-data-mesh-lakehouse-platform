import os
import json
import random
from datetime import datetime, timedelta

def generate_data():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cust_dir = os.path.join(base_dir, "storage", "raw", "customers_data")
    sales_dir = os.path.join(base_dir, "storage", "raw", "sales_data")
    
    # Clean previous raw directories to generate fresh data
    for d in [cust_dir, sales_dir]:
        if os.path.exists(d):
            for f in os.listdir(d):
                os.remove(os.path.join(d, f))
        os.makedirs(d, exist_ok=True)
    
    # 1. Generate Customers (150 active/inactive customers)
    customers = []
    # Real-looking names
    first_names = ["Abner", "Maria", "Carlos", "Beatriz", "João", "Ana", "Lucas", "Julia", "Pedro", "Camila", "Bruno", "Amanda", "Gabriel", "Letícia"]
    last_names = ["Ridigolo", "Silva", "Souza", "Santos", "Oliveira", "Pereira", "Lima", "Ferreira", "Costa", "Rodrigues", "Almeida", "Nascimento"]
    
    random.seed(42)  # For reproducibility
    
    for c_id in range(1001, 1151):
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        email = f"{name.lower().replace(' ', '.')}@example.com"
        # Signup dates distributed over the last 180 days
        signup_days_ago = random.randint(0, 180)
        created_at = datetime.now() - timedelta(days=signup_days_ago)
        # 15% are inactive
        status = "inactive" if random.random() < 0.15 else "active"
        
        customers.append({
            "id": c_id,
            "name": name,
            "email": email,
            "created_at": created_at.isoformat(),
            "status": status
        })
        
    # Add 2 invalid customers for quarantine tests
    customers.append({"id": 9991, "name": "Erro Email", "email": "email_invalido_sem_arroba", "created_at": datetime.now().isoformat(), "status": "active"})
    customers.append({"id": 9992, "name": "Erro Status", "email": "error@example.com", "created_at": datetime.now().isoformat(), "status": "suspended"})

    # Write customers as individual files
    for cust in customers:
        file_path = os.path.join(cust_dir, f"customer_{cust['id']}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(cust, f, indent=2)

    # 2. Generate Sales (180 days with price elasticity)
    products = {
        "Monitor LG 29 Ultrawide": {"base_price": 1300.00, "base_demand": 1.5, "elasticity": 2.5},
        "Teclado Mecânico Keychron": {"base_price": 600.00, "base_demand": 2.5, "elasticity": 3.0},
        "Mouse Ergonômico Vertical": {"base_price": 200.00, "base_demand": 4.0, "elasticity": 2.0},
        "Fone Sony WH-1000XM4": {"base_price": 1700.00, "base_demand": 1.5, "elasticity": 4.0},
        "Curso de Analytics Engineering": {"base_price": 299.90, "base_demand": 3.0, "elasticity": 5.0}
    }
    
    sale_id_counter = 5001
    
    # Loop backwards through 180 days to create daily sales files
    for day_offset in range(180, -1, -1):
        target_date = datetime.now() - timedelta(days=day_offset)
        daily_sales = []
        
        for prod_name, config in products.items():
            # Determine discount for today: 40% chance of a discount up to 30%
            discount = 0.0
            if random.random() < 0.40:
                discount = round(random.uniform(0.05, 0.30), 2)
                
            price = round(config["base_price"] * (1 - discount), 2)
            
            # Competitor price fluctuates slightly around base price (no relation to our discount)
            competitor_price = round(config["base_price"] * random.uniform(0.92, 1.05), 2)
            
            # Demand is higher when discount is higher
            # Q = base_demand * (1 + elasticity * discount) + random noise
            expected_demand = config["base_demand"] * (1.0 + config["elasticity"] * discount)
            actual_quantity = max(0, int(expected_demand + random.gauss(0, 1.0)))
            
            # Generate sales records for this product today
            for _ in range(actual_quantity):
                cust_id = random.randint(1001, 1150)
                # Random hour of day
                sale_time = target_date.replace(
                    hour=random.randint(8, 22),
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59)
                )
                
                # Status: 85% COMPLETED, 10% PENDING, 5% CANCELLED
                status_roll = random.random()
                if status_roll < 0.85:
                    status = "COMPLETED"
                elif status_roll < 0.95:
                    status = "PENDING"
                else:
                    status = "CANCELLED"
                    
                daily_sales.append({
                    "sale_id": sale_id_counter,
                    "customer_id": cust_id,
                    "product": prod_name,
                    "amount": price,
                    # We store competitor price in the raw JSON payload to simulate market feed data ingestion
                    "competitor_price": competitor_price,
                    "status": status,
                    "sale_date": sale_time.isoformat()
                })
                sale_id_counter += 1
                
        # Write daily file if there are sales
        if daily_sales:
            file_path = os.path.join(sales_dir, f"sales_{target_date.strftime('%Y-%m-%d')}.json")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(daily_sales, f, indent=2)

    # Add 2 invalid sales for quarantine tests
    invalid_sales = [
        {"sale_id": 99991, "customer_id": 1001, "product": "Cupom de Desconto Negativo", "amount": -50.00, "status": "COMPLETED", "sale_date": datetime.now().isoformat()},
        {"sale_id": 99992, "customer_id": 1002, "product": "Fone Sony WH-1000XM4", "amount": 1699.00, "status": "SHIPPED", "sale_date": datetime.now().isoformat()}
    ]
    file_path = os.path.join(sales_dir, "sales_invalid.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(invalid_sales, f, indent=2)

    print(f"Massa de dados históricos gerada: {len(customers)} clientes, {sale_id_counter - 5001} transações de vendas.")

if __name__ == "__main__":
    generate_data()
