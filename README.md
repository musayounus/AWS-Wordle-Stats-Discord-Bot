# 🟩 Wordle Discord Leaderboard Bot

A smart, AWS-hosted Discord bot that automatically tracks daily Wordle results — including individual posts, `/share` messages, and official summary messages — and updates a leaderboard in real time.

![Python](https://img.shields.io/badge/Python-3.9-blue)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-RDS-blue)
![AWS](https://img.shields.io/badge/Hosted%20on-AWS-232F3E?logo=amazon-aws)

---

## 📌 Features

✅ Parse Wordle scores like `Wordle 1418 3/6` or `/share`  
✅ Read official summary messages:  
```
Here are yesterday's results:
👑 3/6: @Alice @Bob
4/6: @Charlie
X/6: @Dave
```
✅ Auto-detect Wordle number based on date
✅ Slash commands: /leaderboard, /resetleaderboard
✅ Secure DB access via AWS Secrets Manager
✅ Real-time alerts via CloudWatch + SNS
✅ Deployed on EC2 with systemd + file locking

## ⚙️ Tech Stack
Component	Tech
Language	Python 3.9
Framework	discord.py
Database	PostgreSQL 17 on AWS RDS
Hosting	AWS EC2 (t3.micro)
Secrets	AWS Secrets Manager
Monitoring	AWS CloudWatch + SNS
Deployment	systemd (file lock, PID guard)

## 🧠 Bot Logic
Scores are stored as:

CREATE TABLE scores (
  id SERIAL PRIMARY KEY,
  user_id BIGINT,
  username TEXT NOT NULL,
  wordle_number INTEGER NOT NULL,
  date DATE NOT NULL,
  attempts INTEGER, -- NULL if user failed (X/6)
  UNIQUE(username, wordle_number)
);
X/6 is treated as a failed attempt and excluded from average, but counted as a game played.

## 🚀 Usage
Slash Commands:
/leaderboard – Shows top 10 users sorted by lowest average attempts.

/resetleaderboard – Admin-only command to wipe all scores.

Manual Entry:
Just type Wordle 1418 4/6 or share via /share from the official Wordle app.

## 🛡️ Security & Monitoring
.env contains the bot token and is excluded from Git.

DB creds are managed with AWS Secrets Manager.

systemd prevents duplicate instances via lock file + psutil.

CloudWatch logs and alerts notify of failures, CPU spikes, or DB issues.

## 🧾 Logs & Maintenance
# Restart bot
sudo systemctl restart wordle-bot

# View logs
sudo journalctl -u wordle-bot -f

# Backup database
pg_dump -h <RDS_HOST> -U wordleadmin -Fc postgres > backup_$(date +%Y%m%d).dump

## 📬 Contributions & Ideas
Feel free to fork, clone, and suggest improvements via Pull Requests or Issues.

Want to add Charts? Web Dashboard? Voice alerts? Let’s build it! 🎯

## 📜 License
MIT — free to use, share, and modify.

## 🙏 Acknowledgments
discord.py

asyncpg

AWS

Wordle by The New York Times
