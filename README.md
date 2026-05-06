# Tournament Platform

![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)
![Django](https://img.shields.io/badge/Django-5.0-092E20?style=for-the-badge&logo=django)
![License](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)

## About
Tournament Platform is a comprehensive web application designed to streamline the management of programming tournaments. It provides a seamless experience for administrators to organize events, teams to register and submit their work, and jury members to efficiently evaluate submissions. Developed as a collaborative effort by a passionate team of 9th-grade students, this platform makes hosting competitions accessible, transparent, and highly organized.

## Features
- **Admin Control**: Administrators can seamlessly create, manage, and oversee programming tournaments from end to end.
- **Team Portal**: Teams can easily register for tournaments, view assigned tasks, and submit their solutions (including GitHub repository links and video demonstrations).
- **Jury Evaluation**: Dedicated interfaces for jury members to review submissions and provide scores based on predefined categories.
- **Automatic Leaderboards**: The system automatically aggregates scores and generates dynamic leaderboards immediately after evaluations are completed.

## Tech Stack
| Component | Technologies |
| --- | --- |
| **Backend** | Python 3.11, Django 5 |
| **Frontend** | HTML5, Tailwind CSS |
| **Database** | SQLite (Development) → PostgreSQL (Production) |

## Meet the Team
We are an IT team consisting of 5 driven 9th-grade high school students. 

| Role | Details |
| :--- | :--- |
| **Team Lead / Backend** | Core architecture, Django models, views, and routing. |
| **UX/UI Designer** | Interfaces, responsive design, and Tailwind CSS styling. |
| **Product Owner** | Project management, requirements gathering, and task prioritization. |
| **AI Ops** | Artificial Intelligence integrations and operations. |
| **QA Tester** | Manual and automated testing to ensure platform stability. |

## Screenshots
> [!NOTE]
> *[Coming soon]*

## Installation & How to Run

Follow these steps to get the project up and running on your local machine.

### Prerequisites
- Python 3.11+
- Virtual Environment (recommended)

### Step-by-Step Guide
1. **Clone the repository** (or download the ZIP if Git is not installed):
   ```bash
   git clone https://github.com/sigmakawasaki69/tournament-platform.git
   cd tournament-platform
   ```

2. **Create and activate a virtual environment**:
   - On Windows:
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
   - On macOS/Linux:
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install the dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Environment Variables**:
   Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   ```
   *(Make sure to fill in the required variables such as `SECRET_KEY`, `DEBUG`, and database settings in your new `.env` file.)*

5. **Run Database Migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Start the Development Server**:
   ```bash
   python manage.py runserver
   ```
   The application will now be running at `http://localhost:8000/`.

## Project Structure

```text
tournament-platform/
├── core/                  # Core application settings and configurations
├── scripts/               # Helper scripts (e.g., build scripts, management)
├── templates/             # HTML templates styled with Tailwind CSS
├── tournament/            # Main app for tournament logic, tasks, and submissions
├── users/                 # App for user authentication and profiles
├── .env.example           # Template for environment variables
├── .gitignore             # Files and folders ignored by Git
├── EMAIL_SETUP.md         # Documentation for email configurations
├── build.sh               # Deployment build script
├── manage.py              # Django command-line utility
├── render.yaml            # Deployment configuration for Render platform
└── requirements.txt       # Python package dependencies
```

## Contributing
We welcome contributions! Please follow these guidelines:
1. Fork the project.
2. Create your feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## License
This project is licensed under the MIT License - see the LICENSE file for details.
