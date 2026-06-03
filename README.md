# LockNLog – Asset-Aware Security Monitoring & Incident Management System

## Overview

LockNLog is a cybersecurity-focused security monitoring platform designed to improve organizational security visibility through asset-aware monitoring, access control, and incident management. The system classifies assets based on department and criticality, enforces least-privilege access, and assists security teams in tracking and responding to security incidents.

The project demonstrates practical implementation of Security Operations Center (SOC) concepts, Role-Based Access Control (RBAC), risk assessment, and insider threat mitigation using Python and Flask.

---

## Features

### Asset Management

* Register and manage organizational assets
* Categorize assets by department
* Assign criticality levels to assets
* Maintain centralized asset inventory

### Access Control

* Role-Based Access Control (RBAC)
* Asset-Based Access Control
* Least Privilege Enforcement
* User role management

### Incident Management

* Create and track security incidents
* Associate incidents with affected assets
* Assign severity levels
* Record business impact estimates
* Maintain incident history

### Security Monitoring

* Monitor organizational assets
* Generate security recommendations
* Analyze incident trends
* Improve visibility of security risks

### Reporting & Analytics

* Incident summaries
* Asset criticality analysis
* Department-wise security insights
* Historical incident reporting

---

## Tech Stack

| Component       | Technology           |
| --------------- | -------------------- |
| Backend         | Python               |
| Framework       | Flask                |
| Database        | SQLite               |
| Data Analysis   | Pandas               |
| Frontend        | HTML, CSS, Bootstrap |
| Version Control | Git & GitHub         |

---

## System Architecture

```text
+----------------------+
|      Users/Admin     |
+----------+-----------+
           |
           v
+----------------------+
|     Flask Web App    |
+----------+-----------+
           |
   +-------+-------+
   |               |
   v               v
+--------+   +------------+
| Assets |   | Incidents  |
+--------+   +------------+
      \         /
       \       /
        v     v
   +-------------+
   | SQLite DB   |
   +-------------+
           |
           v
+----------------------+
| Analytics & Reports  |
+----------------------+
```

---

## Database Entities

### Users

* User ID
* Username
* Role
* Department

### Assets

* Asset ID
* Asset Name
* Department
* Criticality Level

### Incidents

* Incident ID
* Threat Type
* Severity
* Business Impact
* Status

### Recommendations

* Recommendation ID
* Incident Reference
* Suggested Mitigation

---

## Project Objectives

* Implement secure asset management practices
* Enforce role-based and asset-based access controls
* Reduce insider threat exposure
* Improve incident visibility and response
* Demonstrate SOC-oriented security workflows
* Support cybersecurity awareness and risk management

---

## Security Concepts Demonstrated

* Role-Based Access Control (RBAC)
* Principle of Least Privilege
* Asset Classification
* Incident Response Lifecycle
* Risk Assessment
* Security Monitoring
* Insider Threat Mitigation
* Security Operations Center (SOC) Concepts

---

## Future Improvements

* MySQL/PostgreSQL Integration
* Multi-Factor Authentication (MFA)
* SIEM Integration
* Real-Time Alerting
* Email Notifications
* Threat Intelligence Feeds
* Audit Logging
* REST API Support

---

## Author

**Disha Chaudhury**

B.Tech CSE (Cyber Security)

## License

This project is developed for educational and cybersecurity learning purposes. Feel free to use and modify it for academic and research purposes.

---
