DCF VALUATION WORKBENCH — START HERE

This folder contains a first Streamlit version of your Google Colab DCF model.

FILES
- app.py: the website/app code. You do not need to understand or edit it yet.
- requirements.txt: tells the hosting service which Python packages the app needs.

EASIEST ROUTE TO A PUBLIC WEBSITE (NO VS CODE REQUIRED)
1. Create/sign in to a GitHub account at https://github.com/ if you do not already have one.
2. Create a new repository. Name it: dcf-valuation-workbench
3. Keep it Public for the simplest Streamlit Community Cloud setup. Do not upload confidential company data or secrets.
4. Upload app.py and requirements.txt into the repository using GitHub's website: Add file > Upload files > Commit changes.
5. Go to https://share.streamlit.io/ and sign in with GitHub.
6. Choose Create app, select your repository, choose the main branch, and set the main file path to app.py.
7. Click Deploy. Streamlit will build the app and give you a website link.

TO TEST IT ON YOUR OWN COMPUTER INSTEAD
1. Install Python from https://www.python.org/downloads/ (on Windows, tick “Add Python to PATH” if offered).
2. Put app.py and requirements.txt in the same folder.
3. Open Command Prompt in that folder.
4. Run:  py -m pip install -r requirements.txt
5. Run:  py -m streamlit run app.py
6. Your browser should open the app.

FINANCIAL STATEMENT UPLOAD TEMPLATE
The uploaded CSV/Excel file must contain these exact column headings:
Year, EBIT, Tax_Rate, D&A, CapEx, Receivables, Inventory, Payables
Use one row per year and at least two years. Tax_Rate is entered as a percentage number, e.g. 22 means 22%.

IMPORTANT
This is a starter conversion of the notebook's model and dashboard, not a financial audit. Test it using sample data and independently verify outputs before relying on it. Do not upload confidential data to a public repository.
