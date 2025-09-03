# 🌱 SmartAgri: A Python-Based Web Application with Hedera DLT for Enhanced Agricultural Traceability

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

SmartAgri is a **proof-of-concept web application** designed to address challenges in the agricultural supply chain.  
By integrating a **Python web interface** with the **Hedera Distributed Ledger (DLT)**, the project ensures an immutable, transparent, and auditable system for tracking agricultural products from farm to consumer, improving **trust and data integrity**.

---

## 🛑 Problem Domain

Modern agriculture involves a complex network of **producers, distributors, regulators, and consumers**.  
Key challenges include:

- Lack of transparency and traceability  
- Susceptibility to fraud and data tampering  
- Inefficiencies in managing large-scale supply chain data  
- Increasing consumer demand for provenance and compliance  

Traditional **centralized databases** are siloed and vulnerable, making it hard to establish a **single verifiable source of truth**. This leads to costly recalls, diminished trust, and difficulties in validating claims such as *“organic”* or *“sustainably sourced.”*

---

## ✅ Solution: Hybrid Web + DLT Architecture

SmartAgri bridges this gap with a **hybrid model**:

- 🌐 **Python Web Application (Flask)** – User-friendly portal for data entry and visualization  
- ⛓ **Hedera Network** – Provides immutable, secure, and decentralized audit trails  

This combination delivers both **accessibility** and **trust**, ensuring that once recorded, supply chain events **cannot be altered or deleted**.

---

## 🌟 Core Features

### 🔹 Web Portal Functionalities
- 👤 **User Management** – Role-based access (farmers, distributors, auditors)  
- 📊 **Data Dashboard** – Track product batches and monitor events in real-time  
- 📂 **File Management System** – Upload and manage certifications, harvest reports, shipping manifests  

### 🔹 Hedera DLT-Powered Features
- 🕒 **Immutable Audit Trails** – Chronological logging of events (planting, harvesting, packaging, shipping)  
- 🔒 **Secure Data Logging** – Sensor data (soil, temperature, humidity, quality checks) stored immutably  
- 🪙 **Asset Tokenization (Planned)** – Represent batches/containers as NFTs for custody transfer tracking  

---

## 🏗️ Repository Structure

```
SmartAgri/
│── app.py                 # Main Flask application
│── test_hedera.py          # Hedera integration test script
│── tempCodeRunnerFile.py   # IDE temp file (should be ignored)
│── OIP.jpg                 # Sample image
│── static/                 # CSS, JS, images
│── templates/              # HTML (Jinja2) templates
│── uploads/                # User-uploaded files
```

---

## ⚙️ Technology Stack

| Component         | Technology/Framework         | Purpose |
|-------------------|-----------------------------|---------|
| Backend Logic     | Python 3.x                  | Core application logic |
| Web Framework     | Flask (inferred)            | HTTP routing, template rendering |
| Frontend          | HTML5, CSS3, JavaScript     | UI and interactivity |
| Distributed Ledger| Hedera SDK for Python       | DLT transactions and queries |
| Environment Mgmt. | `python-dotenv`             | Secure config management |

---

## 🔧 Installation & Setup

### 📋 Prerequisites
- Git  
- Python 3.8+  
- pip (Python package installer)  

### 🛠️ Steps

1. **Clone Repository**
   ```bash
   git clone https://github.com/hegdeshashank100/SmartAgri.git
   cd SmartAgri
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   # Linux/Mac
   source venv/bin/activate
   # Windows
   venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   *(If missing, install manually: `flask python-dotenv hedera-sdk-python`)*

4. **Configure Hedera Credentials**
   - Create a `.env` file in the project root:
     ```ini
     HEDERA_ACCOUNT_ID=your-account-id
     HEDERA_PRIVATE_KEY=your-private-key
     ```
   - ⚠️ Add `.env` to `.gitignore` (do not commit secrets)

5. **Run the Application**
   ```bash
   python app.py
   ```
   Open [http://127.0.0.1:5000/](http://127.0.0.1:5000/) in your browser.

---

## 🧑‍💻 Usage & Workflow

- **Farm Manager** → Logs harvest data, uploads certifications → Data immutably stored on Hedera  
- **Supply Chain Auditor** → Searches batch ID → Views complete audit trail with timestamps & verifiable Hedera transaction IDs  

*(Can be verified via Hedera explorers like HashScan or DragonGlass)*

---

## 📸 Screenshots

_Add images or GIFs of login, dashboard, file uploads, and audit trail views._

---

## 🛠️ Contribution Guidelines

1. Fork the repository  
2. Create a feature branch:  
   ```bash
   git checkout -b feature/AmazingFeature
   ```
3. Commit changes:  
   ```bash
   git commit -m "Add AmazingFeature"
   ```
4. Push to branch & open a Pull Request  

- Follow **PEP 8** guidelines for Python code  

---

## 📅 Development Roadmap

- 📡 IoT Sensor Integration (auto-log data like temperature, humidity)  
- 🔗 REST API for external system integration  
- 📊 Advanced Data Analytics (supply chain insights, compliance metrics)  
- 📱 Mobile-Responsive UI  
- ⚖️ Smart Contract Integration (automated compliance checks, agreements)  

---

## 📜 License

This project is licensed under the **MIT License** – see [LICENSE](LICENSE.md) for details.

---

## 👨‍💻 Author

**Shashank Hegde**  
🔗 [GitHub Profile](https://github.com/hegdeshashank100)  
