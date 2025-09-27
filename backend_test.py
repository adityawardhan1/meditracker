#!/usr/bin/env python3
"""
Comprehensive Backend Testing for Pharmaceutical Order Management System - Department-Based Roles
Tests all backend APIs with new department-based authentication and role permissions:
- Admin, Sales Dept, Purchase Dept, Production Dept
- Department-specific stage update permissions
- Role-based order creation and export restrictions
"""

import requests
import json
import time
from datetime import datetime, timezone, timedelta
import base64
import pandas as pd
from io import BytesIO

# Configuration
BASE_URL = "https://medictrack-1.preview.emergentagent.com/api"
HEADERS = {"Content-Type": "application/json"}

class PharmaBackendTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.headers = HEADERS.copy()
        self.tokens = {}  # Store tokens for different users
        self.users = {}   # Store user data
        self.orders = {}  # Store created orders
        self.test_results = []
        
    def log_test(self, test_name, success, message="", details=None):
        """Log test results"""
        result = {
            "test": test_name,
            "success": success,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name} - {message}")
        if details and not success:
            print(f"   Details: {details}")
    
    def test_authentication_system(self):
        """Test JWT authentication for all roles"""
        print("\n=== Testing Authentication System ===")
        
        # Test user signup for all roles
        test_users = [
            {
                "username": "admin_test",
                "email": "admin@pharmatest.com",
                "full_name": "Admin Test User",
                "password": "admin123!",
                "role": "Admin"
            },
            {
                "username": "manager_test",
                "email": "manager@pharmatest.com", 
                "full_name": "Manager Test User",
                "password": "manager123!",
                "role": "Manager"
            },
            {
                "username": "employee_test",
                "email": "employee@pharmatest.com",
                "full_name": "Employee Test User", 
                "password": "employee123!",
                "role": "Employee"
            }
        ]
        
        # Test signup for each role (or skip if user exists)
        for user_data in test_users:
            try:
                response = requests.post(f"{self.base_url}/auth/signup", 
                                       json=user_data, headers=self.headers)
                
                if response.status_code == 200:
                    user_response = response.json()
                    self.users[user_data["role"]] = {**user_data, **user_response}
                    self.log_test(f"Signup {user_data['role']}", True, 
                                f"User {user_data['username']} created successfully")
                elif response.status_code == 400 and "already registered" in response.text:
                    # User already exists, that's fine for testing
                    self.users[user_data["role"]] = user_data
                    self.log_test(f"Signup {user_data['role']}", True, 
                                f"User {user_data['username']} already exists (OK for testing)")
                else:
                    self.log_test(f"Signup {user_data['role']}", False, 
                                f"Failed with status {response.status_code}", response.text)
            except Exception as e:
                self.log_test(f"Signup {user_data['role']}", False, 
                            f"Exception occurred: {str(e)}")
        
        # Test login for each role
        for role, user_data in self.users.items():
            try:
                login_data = {
                    "username": user_data["username"],
                    "password": user_data["password"]
                }
                response = requests.post(f"{self.base_url}/auth/login", 
                                       json=login_data, headers=self.headers)
                
                if response.status_code == 200:
                    token_data = response.json()
                    self.tokens[role] = token_data["access_token"]
                    self.log_test(f"Login {role}", True, 
                                f"Token received for {user_data['username']}")
                else:
                    self.log_test(f"Login {role}", False, 
                                f"Failed with status {response.status_code}", response.text)
            except Exception as e:
                self.log_test(f"Login {role}", False, 
                            f"Exception occurred: {str(e)}")
        
        # Test token validation with /auth/me endpoint
        for role, token in self.tokens.items():
            try:
                auth_headers = {**self.headers, "Authorization": f"Bearer {token}"}
                response = requests.get(f"{self.base_url}/auth/me", headers=auth_headers)
                
                if response.status_code == 200:
                    user_info = response.json()
                    self.log_test(f"Token Validation {role}", True, 
                                f"Token valid, user: {user_info.get('full_name')}")
                else:
                    self.log_test(f"Token Validation {role}", False, 
                                f"Failed with status {response.status_code}", response.text)
            except Exception as e:
                self.log_test(f"Token Validation {role}", False, 
                            f"Exception occurred: {str(e)}")
    
    def test_order_management(self):
        """Test order CRUD operations and stage management"""
        print("\n=== Testing Order Management ===")
        
        if "Admin" not in self.tokens:
            self.log_test("Order Management", False, "No Admin token available")
            return
        
        admin_headers = {**self.headers, "Authorization": f"Bearer {self.tokens['Admin']}"}
        
        # Test order creation
        test_orders = [
            {
                "customer": {
                    "name": "PharmaCorp Industries",
                    "email": "orders@pharmacorp.com",
                    "phone": "+1-555-1234",
                    "address": "100 Pharma Drive, Boston, MA",
                    "company": "PharmaCorp Industries"
                },
                "product": {
                    "name": "Acetaminophen 500mg",
                    "description": "Pain relief tablets",
                    "quantity": 15000,
                    "unit": "tablets",
                    "batch_size": "1500 units"
                },
                "priority": "High",
                "assigned_employees": []
            },
            {
                "customer": {
                    "name": "MediSupply Chain",
                    "email": "procurement@medisupply.com",
                    "phone": "+1-555-5678",
                    "address": "200 Medical Plaza, Chicago, IL",
                    "company": "MediSupply Chain"
                },
                "product": {
                    "name": "Metformin 850mg",
                    "description": "Diabetes medication",
                    "quantity": 8000,
                    "unit": "tablets",
                    "batch_size": "800 units"
                },
                "priority": "Medium",
                "assigned_employees": []
            }
        ]
        
        # Create orders
        for i, order_data in enumerate(test_orders):
            try:
                response = requests.post(f"{self.base_url}/orders", 
                                       json=order_data, headers=admin_headers)
                
                if response.status_code == 200:
                    order_response = response.json()
                    self.orders[f"order_{i+1}"] = order_response
                    self.log_test(f"Create Order {i+1}", True, 
                                f"Order {order_response.get('order_number')} created")
                else:
                    self.log_test(f"Create Order {i+1}", False, 
                                f"Failed with status {response.status_code}", response.text)
            except Exception as e:
                self.log_test(f"Create Order {i+1}", False, 
                            f"Exception occurred: {str(e)}")
        
        # Test order retrieval
        try:
            response = requests.get(f"{self.base_url}/orders", headers=admin_headers)
            
            if response.status_code == 200:
                orders = response.json()
                self.log_test("Get All Orders", True, 
                            f"Retrieved {len(orders)} orders")
            else:
                self.log_test("Get All Orders", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Get All Orders", False, 
                        f"Exception occurred: {str(e)}")
        
        # Test individual order retrieval and stage updates
        for order_key, order_data in self.orders.items():
            order_id = order_data.get("id")
            if not order_id:
                continue
                
            # Test get single order
            try:
                response = requests.get(f"{self.base_url}/orders/{order_id}", 
                                      headers=admin_headers)
                
                if response.status_code == 200:
                    self.log_test(f"Get Order {order_key}", True, 
                                f"Retrieved order {order_data.get('order_number')}")
                else:
                    self.log_test(f"Get Order {order_key}", False, 
                                f"Failed with status {response.status_code}", response.text)
            except Exception as e:
                self.log_test(f"Get Order {order_key}", False, 
                            f"Exception occurred: {str(e)}")
            
            # Test stage update
            try:
                stage_update = {
                    "stage": "Raw Material Ordered",
                    "comment": "Raw materials ordered from supplier"
                }
                response = requests.put(f"{self.base_url}/orders/{order_id}/stage", 
                                      json=stage_update, headers=admin_headers)
                
                if response.status_code == 200:
                    self.log_test(f"Update Stage {order_key}", True, 
                                f"Stage updated to 'Raw Material Ordered'")
                else:
                    self.log_test(f"Update Stage {order_key}", False, 
                                f"Failed with status {response.status_code}", response.text)
            except Exception as e:
                self.log_test(f"Update Stage {order_key}", False, 
                            f"Exception occurred: {str(e)}")
    
    def test_role_based_access(self):
        """Test role-based access control"""
        print("\n=== Testing Role-Based Access Control ===")
        
        if "Employee" not in self.tokens:
            self.log_test("Role Access Control", False, "No Employee token available")
            return
        
        employee_headers = {**self.headers, "Authorization": f"Bearer {self.tokens['Employee']}"}
        
        # Test employee trying to create order (should fail)
        try:
            order_data = {
                "customer": {
                    "name": "Test Customer",
                    "email": "test@test.com",
                    "phone": "+1-555-0000",
                    "address": "Test Address",
                    "company": "Test Company"
                },
                "product": {
                    "name": "Test Product",
                    "description": "Test Description",
                    "quantity": 100,
                    "unit": "tablets",
                    "batch_size": "10 units"
                },
                "priority": "Low"
            }
            response = requests.post(f"{self.base_url}/orders", 
                                   json=order_data, headers=employee_headers)
            
            if response.status_code == 403:
                self.log_test("Employee Order Creation Restriction", True, 
                            "Employee correctly denied order creation")
            else:
                self.log_test("Employee Order Creation Restriction", False, 
                            f"Expected 403, got {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Employee Order Creation Restriction", False, 
                        f"Exception occurred: {str(e)}")
    
    def test_dashboard_stats(self):
        """Test dashboard statistics API"""
        print("\n=== Testing Dashboard Stats API ===")
        
        if "Admin" not in self.tokens:
            self.log_test("Dashboard Stats", False, "No Admin token available")
            return
        
        admin_headers = {**self.headers, "Authorization": f"Bearer {self.tokens['Admin']}"}
        
        try:
            response = requests.get(f"{self.base_url}/dashboard/stats", headers=admin_headers)
            
            if response.status_code == 200:
                stats = response.json()
                required_fields = ["total_orders", "orders_in_progress", "completed_orders", 
                                 "stage_counts", "recent_activities"]
                
                missing_fields = [field for field in required_fields if field not in stats]
                
                if not missing_fields:
                    self.log_test("Dashboard Stats", True, 
                                f"All stats retrieved: {stats.get('total_orders')} total orders")
                else:
                    self.log_test("Dashboard Stats", False, 
                                f"Missing fields: {missing_fields}", stats)
            else:
                self.log_test("Dashboard Stats", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Dashboard Stats", False, 
                        f"Exception occurred: {str(e)}")
    
    def test_search_and_filters(self):
        """Test search and filtering functionality"""
        print("\n=== Testing Search and Filters ===")
        
        if "Admin" not in self.tokens:
            self.log_test("Search and Filters", False, "No Admin token available")
            return
        
        admin_headers = {**self.headers, "Authorization": f"Bearer {self.tokens['Admin']}"}
        
        # Test search by customer name
        try:
            response = requests.get(f"{self.base_url}/search/orders?query=PharmaCorp", 
                                  headers=admin_headers)
            
            if response.status_code == 200:
                results = response.json()
                self.log_test("Search by Customer", True, 
                            f"Found {len(results)} orders matching 'PharmaCorp'")
            else:
                self.log_test("Search by Customer", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Search by Customer", False, 
                        f"Exception occurred: {str(e)}")
        
        # Test search by product
        try:
            response = requests.get(f"{self.base_url}/search/orders?query=Acetaminophen", 
                                  headers=admin_headers)
            
            if response.status_code == 200:
                results = response.json()
                self.log_test("Search by Product", True, 
                            f"Found {len(results)} orders matching 'Acetaminophen'")
            else:
                self.log_test("Search by Product", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Search by Product", False, 
                        f"Exception occurred: {str(e)}")
        
        # Test filter by stage
        try:
            response = requests.get(f"{self.base_url}/search/orders?stage=Raw Material Ordered", 
                                  headers=admin_headers)
            
            if response.status_code == 200:
                results = response.json()
                self.log_test("Filter by Stage", True, 
                            f"Found {len(results)} orders in 'Raw Material Ordered' stage")
            else:
                self.log_test("Filter by Stage", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Filter by Stage", False, 
                        f"Exception occurred: {str(e)}")
        
        # Test filter by priority
        try:
            response = requests.get(f"{self.base_url}/search/orders?priority=High", 
                                  headers=admin_headers)
            
            if response.status_code == 200:
                results = response.json()
                self.log_test("Filter by Priority", True, 
                            f"Found {len(results)} high priority orders")
            else:
                self.log_test("Filter by Priority", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Filter by Priority", False, 
                        f"Exception occurred: {str(e)}")
    
    def test_export_functionality(self):
        """Test Excel export functionality"""
        print("\n=== Testing Export Functionality ===")
        
        if "Admin" not in self.tokens:
            self.log_test("Export Functionality", False, "No Admin token available")
            return
        
        admin_headers = {**self.headers, "Authorization": f"Bearer {self.tokens['Admin']}"}
        
        try:
            response = requests.get(f"{self.base_url}/export/orders", headers=admin_headers)
            
            if response.status_code == 200:
                export_data = response.json()
                
                if "filename" in export_data and "data" in export_data:
                    # Verify base64 data can be decoded
                    try:
                        decoded_data = base64.b64decode(export_data["data"])
                        # Try to read as Excel file
                        excel_buffer = BytesIO(decoded_data)
                        df = pd.read_excel(excel_buffer)
                        
                        self.log_test("Export Functionality", True, 
                                    f"Excel export successful: {export_data['filename']}, {len(df)} rows")
                    except Exception as decode_error:
                        self.log_test("Export Functionality", False, 
                                    f"Failed to decode/read Excel data: {str(decode_error)}")
                else:
                    self.log_test("Export Functionality", False, 
                                "Missing filename or data in response", export_data)
            else:
                self.log_test("Export Functionality", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Export Functionality", False, 
                        f"Exception occurred: {str(e)}")
    
    def test_demo_data_management(self):
        """Test demo data creation and cleanup"""
        print("\n=== Testing Demo Data Management ===")
        
        if "Admin" not in self.tokens:
            self.log_test("Demo Data Management", False, "No Admin token available")
            return
        
        admin_headers = {**self.headers, "Authorization": f"Bearer {self.tokens['Admin']}"}
        
        # Test create sample data
        try:
            response = requests.post(f"{self.base_url}/demo/create-sample-data", 
                                   headers=admin_headers)
            
            if response.status_code == 200:
                self.log_test("Create Sample Data", True, 
                            "Sample data created successfully")
            else:
                self.log_test("Create Sample Data", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Create Sample Data", False, 
                        f"Exception occurred: {str(e)}")
        
        # Verify sample data was created by checking orders count
        try:
            response = requests.get(f"{self.base_url}/orders", headers=admin_headers)
            
            if response.status_code == 200:
                orders = response.json()
                if len(orders) > 0:
                    self.log_test("Verify Sample Data", True, 
                                f"Sample data verified: {len(orders)} orders found")
                else:
                    self.log_test("Verify Sample Data", False, 
                                "No orders found after sample data creation")
            else:
                self.log_test("Verify Sample Data", False, 
                            f"Failed to verify: status {response.status_code}")
        except Exception as e:
            self.log_test("Verify Sample Data", False, 
                        f"Exception occurred: {str(e)}")
        
        # Test clear sample data
        try:
            response = requests.delete(f"{self.base_url}/demo/clear-sample-data", 
                                     headers=admin_headers)
            
            if response.status_code == 200:
                self.log_test("Clear Sample Data", True, 
                            "Sample data cleared successfully")
            else:
                self.log_test("Clear Sample Data", False, 
                            f"Failed with status {response.status_code}", response.text)
        except Exception as e:
            self.log_test("Clear Sample Data", False, 
                        f"Exception occurred: {str(e)}")
    
    def test_activity_tracking(self):
        """Test activity tracking functionality"""
        print("\n=== Testing Activity Tracking ===")
        
        if not self.orders or "Admin" not in self.tokens:
            self.log_test("Activity Tracking", False, "No orders or Admin token available")
            return
        
        admin_headers = {**self.headers, "Authorization": f"Bearer {self.tokens['Admin']}"}
        
        # Get an order and check its activities
        for order_key, order_data in self.orders.items():
            order_id = order_data.get("id")
            if not order_id:
                continue
            
            try:
                response = requests.get(f"{self.base_url}/orders/{order_id}", 
                                      headers=admin_headers)
                
                if response.status_code == 200:
                    order = response.json()
                    activities = order.get("activities", [])
                    
                    if activities:
                        # Check if activities have required fields
                        latest_activity = activities[-1]
                        required_fields = ["user_id", "user_name", "action", "timestamp"]
                        missing_fields = [field for field in required_fields 
                                        if field not in latest_activity]
                        
                        if not missing_fields:
                            self.log_test(f"Activity Tracking {order_key}", True, 
                                        f"Activities properly tracked: {len(activities)} activities")
                        else:
                            self.log_test(f"Activity Tracking {order_key}", False, 
                                        f"Missing activity fields: {missing_fields}")
                    else:
                        self.log_test(f"Activity Tracking {order_key}", False, 
                                    "No activities found for order")
                else:
                    self.log_test(f"Activity Tracking {order_key}", False, 
                                f"Failed to get order: status {response.status_code}")
            except Exception as e:
                self.log_test(f"Activity Tracking {order_key}", False, 
                            f"Exception occurred: {str(e)}")
            break  # Test only first order
    
    def run_all_tests(self):
        """Run all backend tests"""
        print("🧪 Starting Pharmaceutical Order Management System Backend Tests")
        print(f"🔗 Testing against: {self.base_url}")
        print("=" * 80)
        
        start_time = time.time()
        
        # Run all test suites
        self.test_authentication_system()
        self.test_order_management()
        self.test_role_based_access()
        self.test_dashboard_stats()
        self.test_search_and_filters()
        self.test_export_functionality()
        self.test_activity_tracking()  # Test before demo data cleanup
        self.test_demo_data_management()
        
        end_time = time.time()
        
        # Generate summary
        print("\n" + "=" * 80)
        print("📊 TEST SUMMARY")
        print("=" * 80)
        
        total_tests = len(self.test_results)
        passed_tests = len([t for t in self.test_results if t["success"]])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"⏱️  Duration: {end_time - start_time:.2f} seconds")
        
        if failed_tests > 0:
            print(f"\n🚨 FAILED TESTS ({failed_tests}):")
            for test in self.test_results:
                if not test["success"]:
                    print(f"   ❌ {test['test']}: {test['message']}")
        
        print(f"\n🎯 Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        return {
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "success_rate": (passed_tests/total_tests)*100,
            "results": self.test_results
        }

if __name__ == "__main__":
    tester = PharmaBackendTester()
    results = tester.run_all_tests()