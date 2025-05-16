# Stock Tracker

A Python application that generates AI-powered financial analysis reports and presentations from stock ticker symbols.

## Setup

```bash
# Install dependencies
pip install -r agent/requirements.txt

# Create a .env file with your OpenAI API key
echo "OPENAI_API_KEY=your_openai_api_key_here" > agent/.env
```
### Installing `lxml`
The `lxml` library is required for HTML/XML parsing. Depending on your system, follow the instructions below.

#### macOS (Apple Silicon M1/M2)
```bash
conda install -c conda-forge lxml==4.9.3
```

#### Windows/Linux/Other macOS (x86_64)
```bash
pip install lxml==4.9.3
```

## Usage

```bash
# Run the Streamlit application
cd agent
streamlit run main.py
```

Enter a stock ticker symbol or company name, adjust the analysis period if needed, and click "Generate Analysis" to create your financial report.

## MCP Integration for Claude.ai

The `mcp` folder contains Model Context Protocol modules that can be integrated with Claude.ai:

```bash
# Copy the MCP modules to your existing MCP server project
cp -r mcp/* /path/to/your/mcp/server/project/
```

Follow the Model Context Protocol tutorial provided by Claude.ai for implementation details: https://modelcontextprotocol.io/introduction
