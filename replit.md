# Overview

CBOSA Bot is an automated legal newsletter system that scrapes Polish administrative court judgments from the CBOSA (Central Database of Administrative Court Judgments) database, analyzes them using AI, and distributes legal newsletters to subscribers via email. The system runs on a scheduled basis, processing court decisions and generating professional legal analyses for legal professionals.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Backend Architecture

The system uses a **hybrid Node.js/Python architecture** with clear separation of concerns:

- **Node.js Core**: Handles scheduling, database operations, email services, and orchestration using TypeScript
- **Python Workers**: Executes web scraping, AI analysis, and document processing tasks via child processes
- **Scheduler**: Uses `node-cron` to trigger automated runs every Monday at 7:00 AM (Europe/Warsaw timezone)

## Database Design

The system uses **PostgreSQL with Drizzle ORM** for data persistence, featuring:

- **Users table**: Stores subscriber information and active status
- **Search Configurations table**: Defines search parameters and criteria for CBOSA queries  
- **User Subscriptions table**: Links users to specific search configurations they want to receive
- **Execution Logs table**: Tracks bot runs, success/failure status, and processing statistics
- **Email Logs table**: Records email delivery status and details for audit purposes

The database design supports multi-tenant subscriptions where users can subscribe to different types of legal content based on search configurations.

## Web Scraping Architecture

The Python-based scraping system implements:

- **Rate-limited requests**: Configurable delays between requests to respect CBOSA servers
- **Session persistence**: Maintains cookies and headers across requests
- **Date filtering**: Supports both CBOSA native date filtering and local post-processing
- **RTF document extraction**: Downloads and processes Rich Text Format court decisions
- **Error handling**: Robust retry logic and graceful degradation

## AI Analysis Pipeline

The system integrates OpenAI's GPT-4o model for legal document analysis:

- **Structured prompts**: Uses carefully crafted Polish-language prompts for legal analysis
- **Newsletter formatting**: Generates professional legal newsletters with case summaries
- **Case signature extraction**: Identifies and parses Polish court case reference numbers
- **Content standardization**: Ensures consistent output format across all analyses

## Email Distribution System

Uses **Brevo (formerly SendinBlue)** for transactional email delivery:

- **Template-based emails**: Generates HTML newsletters with consistent formatting
- **Batch processing**: Handles multiple recipients efficiently
- **Delivery tracking**: Logs email send status and handles failures gracefully
- **Professional formatting**: Creates publication-ready legal newsletters

# External Dependencies

## Core Services

- **Neon Database**: PostgreSQL database hosting with serverless architecture
- **Brevo API**: Transactional email service for newsletter distribution
- **OpenAI API**: GPT-4o model for legal document analysis and newsletter generation

## Python Dependencies

- **requests + BeautifulSoup**: Web scraping and HTML parsing for CBOSA interaction
- **striprtf**: RTF document format processing for court decisions
- **openai**: Official OpenAI API client for AI analysis
- **python-docx**: Microsoft Word document generation (optional output format)

## Node.js Dependencies

- **@neondatabase/serverless**: Database connectivity with WebSocket support
- **drizzle-orm**: Type-safe ORM for PostgreSQL operations
- **node-cron**: Reliable task scheduling for automated bot execution
- **@getbrevo/brevo**: Official Brevo API client for email services
- **ws**: WebSocket implementation required by Neon database client

## Integration Points

- **CBOSA Website**: Polish administrative court database (https://orzeczenia.nsa.gov.pl)
- **Date filtering**: Processes Polish date formats and court-specific date fields
- **Legal document processing**: Handles RTF files containing Polish court decisions
- **Timezone handling**: Configured for Europe/Warsaw timezone for Polish legal calendar