# 🟩 Wordle Discord Leaderboard Bot

An AWS-hosted Discord bot that automatically tracks daily Wordle results, including individual posts (e.g. `Wordle 1418 3/6`), `/share` messages (official Wordle app command), and official daily summary messages (official Wordle app end-of-the-day message), and updates a leaderboard in real time.

![Python](https://img.shields.io/badge/Python-3.9-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-RDS-blue)
![AWS](https://img.shields.io/badge/Hosted%20on-AWS-232F3E?logo=amazon-aws)

---

## 📌 Features

✅ Parse Wordle scores like `Wordle 1418 3/6` or `/share`  

✅ Extract player data from official daily summary messages  

✅ Auto-detect Wordle number based on the current date  

✅ Slash commands: `/leaderboard`, `/resetleaderboard`  

✅ Duplicate submission protection (DB constraints)  

✅ Robust infrastructure monitoring (CloudWatch + SNS)  

✅ Secure credentials (AWS Secrets Manager)  

✅ Fully hosted on AWS using EC2 + RDS + systemd  

---

## ☁️ Hosted & Powered by AWS

This bot is designed for **resilient, secure, 24/7 deployment** using AWS services:

| Component        | AWS Service             | Purpose                                                   |
|------------------|--------------------------|------------------------------------------------------------|
| 💻 Hosting        | EC2 (Amazon Linux 2)     | Runs the Python bot 24/7 using a systemd-managed process   |
| 🛢️ Database       | Amazon RDS (PostgreSQL)  | Stores all Wordle scores with automatic backups & scaling  |
| 🔐 Secrets        | AWS Secrets Manager      | Securely manages database credentials                     |
| 🧑‍💼 Permissions	   | IAM Roles + Policies	      | Enforces least-privilege access for EC2 (Secrets Manager, CloudWatch) |
| 📈 Monitoring     | CloudWatch               | Tracks logs, resource usage, and sends alerts              |
| 🔔 Notifications  | SNS (Simple Notification Service) | Sends email/SMS alerts on CPU spikes, DB overload         |
| 🌐 Networking	    |Amazon VPC + Security Groups | Controls traffic to EC2 & RDS, with locked-down ingress/egress rules |
---

### 📊 Architecture Diagram

```mermaid
graph TD
  Discord[Discord Users]
  Bot[EC2 Bot - discord py]
  RDS[Amazon RDS - PostgreSQL]
  Secrets[AWS Secrets Manager]
  IAM[IAM Role]
  CW[CloudWatch Logs and Metrics]
  SNS[SNS Alerts]
  VPC[VPC - Private Network]

  Discord --> Bot
  Bot --> RDS
  Bot --> Secrets
  Bot --> CW
  CW --> SNS
  IAM --> Bot
  RDS --> VPC
```

---

## ⚙️ Tech Stack

| Component           | Tech                                |
|---------------------|-------------------------------------|
| Language            | Python 3.9                          |
| Framework           | discord.py                          |
| Database            | PostgreSQL 17 on AWS RDS            |
| Hosting             | AWS EC2 (t2.micro)                  |
| Secrets             | AWS Secrets Manager                 |
| Monitoring          | AWS CloudWatch + SNS                |
| Deployment          | systemd (file lock, PID guard)      |

---
## 🧠 Bot Logic

- Scores are stored as:

```sql
CREATE TABLE scores (
  id SERIAL PRIMARY KEY,
  user_id BIGINT,
  username TEXT NOT NULL,
  wordle_number INTEGER NOT NULL,
  date DATE NOT NULL,
  attempts INTEGER, -- NULL if user failed (X/6)
  UNIQUE(username, wordle_number)
);
```

- `X/6` is treated as a failed attempt and excluded from average.

---

## 🚀 Usage
### Slash Commands:
- `/leaderboard` – Shows top 10 users sorted by lowest average attempts.
  
- `/resetleaderboard` – Admin-only command to wipe all scores.

### Accepted Formats:
- `Wordle 1418 3/6`

- `/share` from the Wordle app

- Summary messages like:
```
Here are yesterday's results:
👑 2/6: @Alice
4/6: @Bob
X/6: @Charlie
```

---

## 🔐 Security & Monitoring
- `.env` stores Discord bot token (never committed to Git)

- Database credentials are stored in AWS Secrets Manager  

- The bot runs as a systemd service, with:
  - File lock + PID protection (no duplicate instances)
    
  - Auto-restart on crash

- CloudWatch logs:
  - `/wordle-bot/application`
    
  - `/wordle-bot/system`

- SNS notifications alert on:
  - High CPU
  
  - RDS connection issues
    
  - Service restarts or failures

---

## 🧾 Logs & Maintenance
```
# Restart bot  
sudo systemctl restart wordle-bot

# View logs  
sudo journalctl -u wordle-bot -f

# Backup database  
pg_dump -h <RDS_HOST> -U wordleadmin -Fc postgres > backup_$(date +%Y%m%d).dump
```

---

## 📬 Contributions & Ideas
Feel free to fork, clone, and suggest improvements via Pull Requests or Issues.

Want to add Charts? Web Dashboard? Voice alerts? Let’s build it! 🎯

---

## 📜 License
- MIT — free to use, share, and modify.

---

## 🙏 Acknowledgments
- discord.py  
- asyncpg  
- AWS  
- Wordle by The New York Times  
