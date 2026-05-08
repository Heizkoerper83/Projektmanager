"""Graphical user interface for the local project management tool."""

from __future__ import annotations

from datetime import date
import os
import json
import re
import socket
import threading
import tkinter as tk
import webbrowser
import random
import string
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path

from pmtool.collab_accounts import (
    DEFAULT_ACCOUNTS_PATH,
    activate_account,
    authenticate,
    create_account,
    list_accounts,
    set_account_enabled,
    set_account_role,
    set_password,
)
from pmtool.core import (
    add_milestone,
    add_project,
    add_task,
    add_task_note,
    add_template,
    complete_task,
    create_task_from_template,
    delete_milestone,
    delete_project,
    delete_task,
    delete_template,
    export_csv,
    export_json,
    build_weekly_project_report_markdown,
    generate_weekly_project_report,
    get_task,
    import_csv,
    import_json,
    init_db,
    list_milestones,
    list_project_shares,
    list_projects,
    list_task_history,
    list_task_notes,
    list_tasks,
    list_templates,
    share_project,
    unshare_project,
    update_milestone,
    update_project,
    update_task,
    update_template,
    set_current_principal,
    current_principal,
)
from pmtool.ui.common import id_from_labeled_value
from pmtool.ui.dialogs import DatePickerDialog, PlaceholderEntry, ProjectDialog, TaskDialog, TemplateDialog, TogglePasswordEntry
from pmtool.ui.tabs import (
    build_backup_tab,
    build_board_tab,
    build_dashboard_tab,
    build_projects_tab,
    build_reports_tab,
    build_tasks_tab,
    build_timeline_tab,
    build_templates_tab,
    due_filter_value,
    energy_filter_value,
    open_project_in_tasks_tab as tabs_open_project_in_tasks_tab,
    open_selected_project_task as tabs_open_selected_project_task,
    open_selected_project_template as tabs_open_selected_project_template,
    refresh_board as tabs_refresh_board,
    refresh_dashboard as tabs_refresh_dashboard,
    refresh_projects as tabs_refresh_projects,
    refresh_tasks as tabs_refresh_tasks,
    refresh_timeline as tabs_refresh_timeline,
    refresh_templates as tabs_refresh_templates,
    selected_milestone_id as tabs_selected_milestone_id,
    selected_project_tree_id as tabs_selected_project_tree_id,
    selected_task_id as tabs_selected_task_id,
    selected_template_id as tabs_selected_template_id,
    status_filter_value,
    update_active_milestone as tabs_update_active_milestone,
    update_active_template as tabs_update_active_template,
    update_project_milestones as tabs_update_project_milestones,
    update_task_details as tabs_update_task_details,
)


TARGET_PROJECT_OWNER_EMAIL = "florian.burtscher.at@icloud.com"


def _search_terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9][a-z0-9+#._-]*", query.lower()) if term]


def _match_score(query: str, title: object, *parts: object) -> int:
    terms = _search_terms(query)
    if not terms:
        return 0
    title_text = str(title or "").lower()
    other_text = " ".join(str(part or "") for part in parts).lower()
    score = 0
    for term in terms:
        if term in title_text:
            score += 5 if title_text.startswith(term) else 3
        elif term in other_text:
            score += 1
        else:
            return 0
    query_lower = query.lower()
    if title_text.startswith(query_lower):
        score += 7
    elif query_lower in title_text:
        score += 5
    return score


def _matches_search(query: str, *parts: object) -> bool:
    if not parts:
        return False
    return _match_score(query, parts[0], *parts[1:]) > 0


def _truncate_preview(text: object, limit: int = 80) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _validate_email(email: str) -> tuple[bool, str]:
    """Validate email format."""
    import re
    email = email.strip()
    if not email:
        return False, "E-Mail darf nicht leer sein"
    # simple regex for basic email validation
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, email):
        return False, "Ungültiges E-Mail-Format (z.B. name@example.com)"
    if len(email) > 254:
        return False, "E-Mail-Adresse zu lang (max 254 Zeichen)"
    return True, ""


def _check_password_strength(password: str) -> tuple[str, str]:
    """Check password strength and return (strength, color)."""
    password = password.strip()
    if len(password) < 8:
        return "Schwach", "#c62828"  # red
    
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password)
    
    score = sum([has_lower, has_upper, has_digit, has_special])
    
    if score < 2:
        return "Schwach", "#c62828"  # red
    elif score < 3:
        return "Mittel", "#f57c00"  # orange
    else:
        return "Stark", "#2e7d32"  # green


def _get_last_login_email() -> str:
    """Get last used email from cache file."""
    try:
        cache_file = Path.home() / ".pmtool_last_email"
        if cache_file.exists():
            return cache_file.read_text().strip()
    except Exception:
        pass
    return ""


def _save_last_login_email(email: str) -> None:
    """Save last used email to cache file."""
    try:
        cache_file = Path.home() / ".pmtool_last_email"
        cache_file.write_text(email.strip())
    except Exception:
        pass


def _log_audit_event(email: str, action: str, details: str = "") -> None:
    """Log audit event for admin users."""
    try:
        from datetime import datetime
        audit_file = Path.home() / ".pmtool_audit.jsonl"
        event = {
            "timestamp": datetime.now().isoformat(),
            "user": email,
            "action": action,
            "details": details
        }
        with open(audit_file, "a") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


class LoginDialog(tk.Toplevel):
    """Dialog for user login and registration."""
    
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("Anmelden oder Registrieren")
        self.geometry("420x380")
        self.resizable(False, False)
        self.current_user: dict[str, str] | None = None
        
        self.transient(parent)
        self.grab_set()
        
        # Main frame with notebook for tabs
        main_frame = ttk.Frame(self, padding=14)
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(main_frame, text="Projektmanager", style="Header.TLabel").pack(anchor="w", pady=(0, 8))
        
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True, pady=(0, 14))
        
        # Login tab
        login_frame = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(login_frame, text="Anmelden")
        
        ttk.Label(login_frame, text="E-Mail:").pack(anchor="w", pady=(0, 2))
        self.login_email = PlaceholderEntry(login_frame, placeholder="name@example.com", width=40)
        self.login_email.pack(fill="x", pady=(0, 12))
        # Load and set last used email
        last_email = _get_last_login_email()
        if last_email:
            self.login_email.insert(0, last_email)
        self.login_email.focus()
        
        ttk.Label(login_frame, text="Passwort:").pack(anchor="w", pady=(0, 2))
        self.login_password_var = tk.StringVar()
        self.login_password = TogglePasswordEntry(login_frame, variable=self.login_password_var, width=40)
        self.login_password.pack(fill="x", pady=(0, 14))
        self.login_password.entry.bind("<Return>", lambda _: self._on_login())
        
        ttk.Button(login_frame, text="Anmelden", style="Accent.TButton", command=self._on_login).pack(fill="x")
        self.login_error = ttk.Label(login_frame, text="", foreground="#c62828")
        self.login_error.pack(anchor="w", pady=(10, 0))
        
        # Account deletion link
        ttk.Button(login_frame, text="Account löschen", command=self._on_delete_account).pack(anchor="w", pady=(10, 0))
        ttk.Button(login_frame, text="Passwort vergessen?", command=self._on_reset_password).pack(anchor="w", pady=(4, 0))
        
        # Register tab
        register_frame = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(register_frame, text="Registrieren")
        
        ttk.Label(register_frame, text="E-Mail:").pack(anchor="w", pady=(0, 2))
        self.reg_email = PlaceholderEntry(register_frame, placeholder="name@example.com", width=40)
        self.reg_email.pack(fill="x", pady=(0, 10))

        
        ttk.Label(register_frame, text="Passwort (mind. 8 Zeichen):").pack(anchor="w", pady=(0, 2))
        self.reg_password_var = tk.StringVar()
        self.reg_password = TogglePasswordEntry(register_frame, variable=self.reg_password_var, width=40)
        self.reg_password.pack(fill="x", pady=(0, 2))
        
        # Password strength indicator
        self.password_strength_frame = ttk.Frame(register_frame)
        self.password_strength_frame.pack(fill="x", pady=(0, 10))
        self.password_strength_label = ttk.Label(self.password_strength_frame, text="Stärke: ", foreground="gray")
        self.password_strength_label.pack(side="left")
        
        # Bind password change to update strength
        self.reg_password_var.trace_add("write", lambda *_: self._update_password_strength())
        
        ttk.Label(register_frame, text="Passwort wiederholen:").pack(anchor="w", pady=(0, 2))
        self.reg_password_confirm_var = tk.StringVar()
        self.reg_password_confirm = TogglePasswordEntry(register_frame, variable=self.reg_password_confirm_var, width=40)
        self.reg_password_confirm.pack(fill="x", pady=(0, 14))
        self.reg_password_confirm.entry.bind("<Return>", lambda _: self._on_register())
        
        ttk.Button(register_frame, text="Registrieren", style="Accent.TButton", command=self._on_register).pack(fill="x")
        self.reg_error = ttk.Label(register_frame, text="", foreground="#c62828")
        self.reg_error.pack(anchor="w", pady=(10, 0))
        
        # Set focus order for keyboard navigation (Tab key)
        self.login_email.focus_set()
        self._setup_focus_order()
    
    def _update_password_strength(self) -> None:
        """Update password strength indicator."""
        password = self.reg_password_var.get()
        strength, color = _check_password_strength(password)
        self.password_strength_label.config(text=f"Stärke: {strength}", foreground=color)
    
    def _setup_focus_order(self) -> None:
        """Set up tab key focus order in login and register tabs."""
        # This ensures that when Tab is pressed, focus moves in a defined order
        # Tkinter handles this automatically with the pack/grid order, but we
        # can reinforce it if needed. The default behavior is usually sufficient.
        pass
    
    def _on_delete_account(self) -> None:
        """Handle account deletion."""
        from pmtool.collab_accounts import delete_account
        from tkinter import simpledialog, messagebox
        
        # Ask for email
        email = simpledialog.askstring("Account löschen", "E-Mail des Accounts:", parent=self)
        if not email:
            return
        
        # Ask for password confirmation
        password = simpledialog.askstring("Account löschen", "Passwort zur Bestätigung:", parent=self, show="*")
        if not password:
            return
        
        # Confirm deletion
        result = messagebox.askyesno(
            "Account löschen",
            f"Möchtest du den Account {email} wirklich löschen?\n\nDiese Aktion kann nicht rückgängig gemacht werden!"
        )
        if not result:
            return
        
        try:
            # Verify password by attempting login
            from pmtool.collab_accounts import authenticate
            if not authenticate(email, password, path=DEFAULT_ACCOUNTS_PATH):
                messagebox.showerror("Fehler", "❌ E-Mail oder Passwort stimmt nicht")
                return
            
            # Delete account via account service to keep file format consistent
            delete_account(email, path=DEFAULT_ACCOUNTS_PATH)
            
            _log_audit_event(email, "DELETE_ACCOUNT", "Account self-deleted")
            messagebox.showinfo("Erfolg", f"Account {email} wurde gelöscht.")
        except Exception as e:
            messagebox.showerror("Fehler", f"❌ Fehler beim Löschen: {str(e)}")
    
    def _on_reset_password(self) -> None:
        """Handle password reset."""
        from tkinter import simpledialog, messagebox
        from pmtool.collab_accounts import set_password
        
        # Ask for email
        email = simpledialog.askstring("Passwort zurücksetzen", "E-Mail des Accounts:", parent=self)
        if not email:
            return
        
        # Validate email format
        valid, msg = _validate_email(email)
        if not valid:
            messagebox.showerror("Fehler", f"❌ {msg}")
            return
        
        # Generate a temporary password that always meets minimum length
        temp_password = "".join(random.choices(string.ascii_letters + string.digits, k=12))
        
        try:
            # Set new temporary password (this will raise ValueError if account not found)
            set_password(email, temp_password, path=DEFAULT_ACCOUNTS_PATH)
            
            # Show temporary password
            messagebox.showinfo(
                "Passwort zurückgesetzt",
                f"Temporäres Passwort: {temp_password}\n\n"
                f"Bitte ändere dein Passwort nach dem Anmelden!"
            )
            _log_audit_event(email, "PASSWORD_RESET", "User requested password reset")
        except ValueError as ve:
            messagebox.showerror("Fehler", f"❌ {str(ve)}")
        except Exception as e:
            messagebox.showerror("Fehler", f"❌ Fehler beim Zurücksetzen: {str(e)}")
    
    def _on_login(self) -> None:
        """Handle login."""
        email = self.login_email.get_value()
        password = self.login_password_var.get().strip()
        
        if not email:
            self.login_error.config(text="❌ E-Mail-Adresse eingeben")
            return
        if not password:
            self.login_error.config(text="❌ Passwort eingeben")
            return
        
        # validate email format
        valid, msg = _validate_email(email)
        if not valid:
            self.login_error.config(text=f"❌ {msg}")
            return
        
        try:
            result = authenticate(email, password, DEFAULT_ACCOUNTS_PATH)
            if result:
                # assign admin role only to florian.burtscher.at@icloud.com
                assigned_role = "admin" if email.lower() == "florian.burtscher.at@icloud.com" else result.get("role", "reader")
                # inform core about current principal (name + role)
                try:
                    set_current_principal({"name": email, "role": assigned_role})
                except Exception:
                    pass
                self.current_user = {"email": email, "name": result.get("name", email), "role": assigned_role}
                _save_last_login_email(email)
                _log_audit_event(email, "LOGIN", f"Role: {assigned_role}")
                self.destroy()
            else:
                self.login_error.config(text="❌ E-Mail oder Passwort stimmt nicht")
                self.login_password_var.set("")
        except ValueError as exc:
            self.login_error.config(text=f"❌ Fehler: {str(exc)}")
    
    def _on_register(self) -> None:
        """Handle registration."""
        email = self.reg_email.get_value()
        password = self.reg_password_var.get().strip()
        password_confirm = self.reg_password_confirm_var.get().strip()
        
        if not email:
            self.reg_error.config(text="❌ E-Mail-Adresse erforderlich")
            return
        if not password:
            self.reg_error.config(text="❌ Passwort erforderlich")
            return
        if not password_confirm:
            self.reg_error.config(text="❌ Passwort-Bestätigung erforderlich")
            return
        
        # validate email format
        valid, msg = _validate_email(email)
        if not valid:
            self.reg_error.config(text=f"❌ {msg}")
            return
        
        if password != password_confirm:
            self.reg_error.config(text="❌ Passwörter stimmen nicht überein")
            self.reg_password_confirm_var.set("")
            return
        
        if len(password) < 8:
            self.reg_error.config(text="❌ Passwort muss mind. 8 Zeichen lang sein")
            return
        
        try:
            # New accounts default to reader role
            assigned_role = "reader"
            account = create_account(email, password, role=assigned_role, path=DEFAULT_ACCOUNTS_PATH)
            set_account_enabled(account["email"], True, path=DEFAULT_ACCOUNTS_PATH)
            try:
                set_current_principal({"name": account.get("email", email), "role": account.get("role", assigned_role)})
            except Exception:
                pass
            self.current_user = {"email": email, "name": account.get("email", email), "role": assigned_role}
            _save_last_login_email(email)
            _log_audit_event(email, "REGISTER", f"Role: {assigned_role}")
            self.destroy()
        except ValueError as exc:
            self.reg_error.config(text=f"❌ {str(exc)}")
            self.reg_password_var.set("")
            self.reg_password_confirm_var.set("")


class EmailSharingDialog(tk.Toplevel):
    """Dialog for selecting an email to share a project with."""
    
    def __init__(self, parent: tk.Tk, title: str = "E-Mail für Freigabe") -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("400x300")
        self.resizable(False, False)
        self.result: str | None = None
        
        self.transient(parent)
        self.grab_set()
        
        # Load available accounts
        try:
            accounts = list_accounts(DEFAULT_ACCOUNTS_PATH)
            self.email_list = [str(acc.get("email", "")).strip() for acc in accounts if str(acc.get("email", "")).strip()]
        except Exception:
            self.email_list = []
        
        # Label
        ttk.Label(self, text="Verfügbare Accounts:", style="Header.TLabel").pack(anchor="w", padx=10, pady=(10, 5))
        
        # Listbox with available accounts
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
        
        self.listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set, height=8)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        
        for email in self.email_list:
            self.listbox.insert(tk.END, email)
        
        self.listbox.bind("<Double-1>", lambda _: self._on_select())
        
        # Manual email entry
        ttk.Label(self, text="Oder geben Sie ein E-Mail ein:").pack(anchor="w", padx=10, pady=(10, 2))
        self.email_var = tk.StringVar()
        self.email_entry = PlaceholderEntry(self, placeholder="name@example.com", textvariable=self.email_var)
        self.email_entry.pack(fill="x", padx=10, pady=(0, 10))
        
        # Buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(button_frame, text="Bestätigen", command=self._on_ok).pack(side="left", padx=(0, 5))
        ttk.Button(button_frame, text="Abbrechen", command=self._on_cancel).pack(side="left")
        
        self.after(100, lambda: self.email_var.set(""))
    
    def _on_select(self) -> None:
        """Handle selection from listbox."""
        selection = self.listbox.curselection()
        if selection:
            self.result = self.email_list[selection[0]]
            self.destroy()
    
    def _on_ok(self) -> None:
        """Handle OK button."""
        email_value = self.email_entry.get_value()
        if email_value:
            self.result = email_value
        elif self.listbox.curselection():
            self.result = self.email_list[self.listbox.curselection()[0]]
        self.destroy()
    
    def _on_cancel(self) -> None:
        """Handle Cancel button."""
        self.result = None
        self.destroy()


class AccountMenuDialog(tk.Toplevel):
    """Dialog for account management menu."""

    def __init__(self, parent: tk.Tk, email: str, relogin_callback) -> None:
        super().__init__(parent)
        self.email = email
        self.relogin_callback = relogin_callback
        self.title("Mein Konto")
        self.geometry("350x200")
        self.resizable(False, False)
        self.grab_set()
        
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Kontoeinstellungen", style="Header.TLabel").pack(anchor="w", pady=(0, 20))
        
        # Buttons for different actions
        ttk.Button(
            frame,
            text="🔐 Passwort ändern",
            command=self._on_change_password,
            width=30
        ).pack(fill="x", pady=(0, 8))
        
        ttk.Button(
            frame,
            text="🔄 Mit anderem Account anmelden",
            command=self._on_switch_account,
            width=30
        ).pack(fill="x", pady=(0, 8))
        
        ttk.Button(
            frame,
            text="🚪 Abmelden",
            command=self._on_logout,
            width=30
        ).pack(fill="x", pady=(0, 8))
        
        ttk.Button(
            frame,
            text="✕ Schließen",
            command=self.destroy,
            width=30
        ).pack(fill="x", pady=(0, 0))
    
    def _on_change_password(self) -> None:
        """Open password change dialog."""
        parent_window = self.master if self.master else self
        self.destroy()
        ChangePasswordDialog(parent_window, self.email)
    
    def _on_switch_account(self) -> None:
        """Switch to another account."""
        self.destroy()
        self.relogin_callback()
    
    def _on_logout(self) -> None:
        """Logout and return to login screen."""
        result = messagebox.askyesno(
            "Bestätigung",
            "Möchtest du dich wirklich abmelden?\n\nEs wird zum Anmeldedialog zurückgegriffen.",
            parent=self
        )
        if result:
            self.destroy()
            self.relogin_callback()


class ChangePasswordDialog(tk.Toplevel):
    """Dialog for changing user password."""

    def __init__(self, parent: tk.Tk, email: str) -> None:
        super().__init__(parent)
        self.email = email
        self.title("Passwort ändern")
        self.geometry("400x300")
        self.resizable(False, False)
        self.grab_set()
        
        frame = ttk.Frame(self, padding=14)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Passwort ändern", style="Header.TLabel").pack(anchor="w", pady=(0, 10))
        
        # Current password
        ttk.Label(frame, text="Aktuelles Passwort:").pack(anchor="w", pady=(0, 2))
        self.current_password_var = tk.StringVar()
        self.current_password = TogglePasswordEntry(frame, variable=self.current_password_var, width=40)
        self.current_password.pack(fill="x", pady=(0, 12))
        
        # New password
        ttk.Label(frame, text="Neues Passwort (mind. 8 Zeichen):").pack(anchor="w", pady=(0, 2))
        self.new_password_var = tk.StringVar()
        self.new_password = TogglePasswordEntry(frame, variable=self.new_password_var, width=40)
        self.new_password.pack(fill="x", pady=(0, 2))
        
        # Password strength indicator
        self.strength_frame = ttk.Frame(frame)
        self.strength_frame.pack(fill="x", pady=(0, 12))
        self.strength_label = ttk.Label(self.strength_frame, text="Stärke: ", foreground="gray")
        self.strength_label.pack(side="left")
        self.new_password_var.trace_add("write", lambda *_: self._update_strength())
        
        # Confirm new password
        ttk.Label(frame, text="Passwort bestätigen:").pack(anchor="w", pady=(0, 2))
        self.confirm_password_var = tk.StringVar()
        self.confirm_password = TogglePasswordEntry(frame, variable=self.confirm_password_var, width=40)
        self.confirm_password.pack(fill="x", pady=(0, 14))
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x")
        ttk.Button(button_frame, text="Ändern", style="Accent.TButton", command=self._on_change).pack(side="left", padx=(0, 6))
        ttk.Button(button_frame, text="Abbrechen", command=self.destroy).pack(side="left")
        
        # Error label
        self.error_label = ttk.Label(frame, text="", foreground="#c62828")
        self.error_label.pack(anchor="w", pady=(10, 0))
    
    def _update_strength(self) -> None:
        """Update password strength indicator."""
        password = self.new_password_var.get()
        strength, color = _check_password_strength(password)
        self.strength_label.config(text=f"Stärke: {strength}", foreground=color)
    
    def _on_change(self) -> None:
        """Handle password change."""
        from pmtool.collab_accounts import authenticate, set_password
        
        current = self.current_password_var.get().strip()
        new = self.new_password_var.get().strip()
        confirm = self.confirm_password_var.get().strip()
        
        if not current:
            self.error_label.config(text="❌ Aktuelles Passwort erforderlich")
            return
        if not new:
            self.error_label.config(text="❌ Neues Passwort erforderlich")
            return
        if not confirm:
            self.error_label.config(text="❌ Passwort-Bestätigung erforderlich")
            return
        
        # Verify current password
        if not authenticate(self.email, current, path=DEFAULT_ACCOUNTS_PATH):
            self.error_label.config(text="❌ Aktuelles Passwort stimmt nicht")
            self.current_password_var.set("")
            return
        
        # Check new password strength
        if len(new) < 8:
            self.error_label.config(text="❌ Passwort muss mind. 8 Zeichen lang sein")
            return
        
        # Verify passwords match
        if new != confirm:
            self.error_label.config(text="❌ Neue Passwörter stimmen nicht überein")
            self.confirm_password_var.set("")
            return
        
        # Change password
        try:
            set_password(self.email, new, path=DEFAULT_ACCOUNTS_PATH)
            _log_audit_event(self.email, "PASSWORD_CHANGED", "User changed own password")
            messagebox.showinfo("Erfolg", "Passwort wurde geändert.", parent=self)
            self.destroy()
        except Exception as e:
            self.error_label.config(text=f"❌ Fehler: {str(e)}")


class AccountAdminDialog(tk.Toplevel):
    """Dialog for managing collaboration accounts."""

    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.title("Konten verwalten")
        self.geometry("760x420")
        self.minsize(700, 380)
        self.resizable(True, True)

        self.transient(parent)
        self.grab_set()

        container = ttk.Frame(self, padding=12)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=3)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(container)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        columns = ("email", "role", "enabled", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("email", text="E-Mail")
        self.tree.heading("role", text="Rolle")
        self.tree.heading("enabled", text="Aktiv")
        self.tree.heading("status", text="Status")
        self.tree.column("email", width=300, anchor="w")
        self.tree.column("role", width=90, anchor="center")
        self.tree.column("enabled", width=70, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self._sync_details())

        details = ttk.Frame(container)
        details.grid(row=0, column=1, sticky="nsew")
        details.columnconfigure(1, weight=1)

        ttk.Label(details, text="Ausgewähltes Konto", style="Header.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.email_var = tk.StringVar()
        self.role_var = tk.StringVar(value="reader")
        self.enabled_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="")

        for row, (label, variable) in enumerate(
            [
                ("E-Mail", self.email_var),
                ("Rolle", self.role_var),
                ("Aktiv", self.enabled_var),
                ("Status", self.status_var),
            ],
            start=1,
        ):
            ttk.Label(details, text=label).grid(row=row, column=0, sticky="w", pady=(0, 2), padx=(0, 8))
            ttk.Entry(details, textvariable=variable, state="readonly").grid(row=row, column=1, sticky="ew", pady=(18 if row == 1 else 0, 8))

        button_row = ttk.Frame(details)
        button_row.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)

        ttk.Button(button_row, text="Aktualisieren", command=self.refresh_accounts).grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        ttk.Button(button_row, text="Aktivieren/Sperren", command=self.toggle_enabled).grid(row=0, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(button_row, text="Rolle setzen", command=self.change_role).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 6))
        ttk.Button(button_row, text="Passwort setzen", command=self.change_password).grid(row=1, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(button_row, text="Aktivierung neu setzen", command=self.activate_selected).grid(row=2, column=0, columnspan=2, sticky="ew")

        self.refresh_accounts()

    def refresh_accounts(self) -> None:
        for child in self.tree.get_children():
            self.tree.delete(child)
        for account in list_accounts(DEFAULT_ACCOUNTS_PATH):
            email = str(account.get("email", "")).strip()
            role = str(account.get("role", "reader"))
            enabled = "Ja" if bool(account.get("enabled", True)) else "Nein"
            status = str(account.get("status", ""))
            self.tree.insert("", tk.END, iid=email, values=(email, role, enabled, status))
        if self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
        self._sync_details()

    def _selected_email(self) -> str | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return str(selection[0])

    def _selected_account(self) -> dict[str, object] | None:
        email = self._selected_email()
        if not email:
            return None
        for account in list_accounts(DEFAULT_ACCOUNTS_PATH):
            if str(account.get("email", "")).strip().lower() == email.lower():
                return account
        return None

    def _sync_details(self) -> None:
        account = self._selected_account()
        if account is None:
            self.email_var.set("")
            self.role_var.set("reader")
            self.enabled_var.set("")
            self.status_var.set("")
            return
        self.email_var.set(str(account.get("email", "")))
        self.role_var.set(str(account.get("role", "reader")))
        self.enabled_var.set("Ja" if bool(account.get("enabled", True)) else "Nein")
        self.status_var.set(str(account.get("status", "")))

    def toggle_enabled(self) -> None:
        account = self._selected_account()
        if account is None:
            return
        email = str(account.get("email", ""))
        enabled = not bool(account.get("enabled", True))
        try:
            set_account_enabled(email, enabled, path=DEFAULT_ACCOUNTS_PATH)
        except ValueError as exc:
            messagebox.showerror("Konten", str(exc), parent=self)
            return
        self.refresh_accounts()

    def change_role(self) -> None:
        account = self._selected_account()
        if account is None:
            return
        email = str(account.get("email", ""))
        current_role = str(account.get("role", "reader"))
        # admin role can only be assigned to florian.burtscher.at@icloud.com via registration
        # prevent changing roles to/from admin in the UI
        if current_role == "admin":
            messagebox.showinfo("Rolle setzen", "Die Admin-Rolle kann nicht geändert werden.", parent=self)
            return
        role = simpledialog.askstring("Rolle setzen", "Neue Rolle (reader/editor):", parent=self, initialvalue=current_role)
        if role is None:
            return
        # only allow reader/editor roles via UI
        if role not in ("reader", "editor"):
            messagebox.showerror("Rolle setzen", "Nur 'reader' oder 'editor' sind erlaubt.", parent=self)
            return
        try:
            set_account_role(email, role, path=DEFAULT_ACCOUNTS_PATH)
        except ValueError as exc:
            messagebox.showerror("Konten", str(exc), parent=self)
            return
        self.refresh_accounts()

    def change_password(self) -> None:
        account = self._selected_account()
        if account is None:
            return
        email = str(account.get("email", ""))
        password = simpledialog.askstring("Passwort setzen", f"Neues Passwort für {email}:", parent=self, show="•")
        if password is None:
            return
        try:
            set_password(email, password, path=DEFAULT_ACCOUNTS_PATH)
        except ValueError as exc:
            messagebox.showerror("Konten", str(exc), parent=self)
            return
        messagebox.showinfo("Konten", "Passwort gesetzt.", parent=self)

    def activate_selected(self) -> None:
        account = self._selected_account()
        if account is None:
            return
        email = str(account.get("email", ""))
        activation_key = simpledialog.askstring("Aktivieren", f"Aktivierungs-API-Key für {email}:", parent=self)
        if activation_key is None:
            return
        try:
            activate_account(email, activation_key, path=DEFAULT_ACCOUNTS_PATH)
        except ValueError as exc:
            messagebox.showerror("Konten", str(exc), parent=self)
            return
        self.refresh_accounts()


class ProjectManagerApp(tk.Tk):
    def __init__(self, user_data: dict[str, object] | None = None) -> None:
        super().__init__()
        init_db()
        try:
            set_account_enabled(TARGET_PROJECT_OWNER_EMAIL, True, path=DEFAULT_ACCOUNTS_PATH)
        except ValueError:
            pass
        
        # Get user - either from provided user_data or show login dialog
        if user_data is not None:
            self.current_user = user_data
        else:
            # Show login dialog (local authentication fallback)
            login_dialog = LoginDialog(self)
            self.wait_window(login_dialog)
            
            if login_dialog.current_user is None:
                # User cancelled login, exit app
                self.destroy()
                return
            
            self.current_user = login_dialog.current_user
        self.title("Projektmanager")
        self.geometry("1400x900")
        self.minsize(1200, 760)
        
        # Session timeout settings (30 minutes = 1800 seconds)
        self.session_timeout_seconds = 1800
        self.session_idle_seconds = 0
        self.session_timeout_id = None

        self.theme_var = tk.StringVar(value="Hell")
        self.search_var = tk.StringVar()
        self.project_filter_var = tk.StringVar(value="Alle Projekte")
        self.status_filter_var = tk.StringVar(value="Alle Aufgaben")
        self.tag_filter_var = tk.StringVar(value="")
        self.context_filter_var = tk.StringVar(value="")
        self.energy_filter_var = tk.StringVar(value="Alle Energien")
        self.due_filter_var = tk.StringVar(value="Alle Fälligkeiten")
        self.quick_title_var = tk.StringVar()
        self.quick_project_var = tk.StringVar(value="Keine Zuordnung")
        self.global_search_var = tk.StringVar()
        self.timeline_project_var = tk.StringVar(value="Projekt wählen")
        self.timeline_status_var = tk.StringVar(value="Bereit")
        self.report_project_var = tk.StringVar(value="Projekt wählen")
        self.report_date_var = tk.StringVar()
        self.report_status_var = tk.StringVar()
        self.report_plan_vars: list[tk.StringVar] = []
        self.report_goal_vars: list[tk.StringVar] = []
        self.report_not_achieved_vars: list[tk.StringVar] = []
        self.report_delay1_var = tk.StringVar()
        self.report_delay2_var = tk.StringVar()
        self.report_milestone_var = tk.StringVar()
        self.report_milestone_date_var = tk.StringVar()
        self.report_status_message_var = tk.StringVar(value="Bereit")
        self.report_project_tasks_cache: list[dict[str, object]] = []
        self.active_task_id: int | None = None
        self.active_template_id: int | None = None
        self.active_project_id: int | None = None
        self.active_milestone_id: int | None = None
        self._search_suggest_after_id: str | None = None
        self._search_suggest_popup: tk.Toplevel | None = None
        self._search_suggest_listbox: tk.Listbox | None = None
        self._search_suggest_results: list[dict[str, object]] = []
        self._search_suggest_max = 6
        self._search_suggest_preview_limit = 60

        self._init_dynamic_report_items()

        self.search_var.trace_add("write", lambda *_: self.refresh_tasks())

        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self._build_ui()
        self.apply_theme()
        self.refresh_all()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x")
        ttk.Label(header, text="Projektmanager", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Persönliches Steuerzentrum mit Kanban, Aufgaben, Projekten, Vorlagen und Backups.",
            style="Subheader.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        topbar = ttk.Frame(container)
        topbar.pack(fill="x", pady=(10, 12))
        ttk.Label(topbar, text="Schnell erfassen").grid(row=0, column=0, sticky="w")
        ttk.Entry(topbar, textvariable=self.quick_title_var, width=42).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.quick_project_combo = ttk.Combobox(topbar, textvariable=self.quick_project_var, state="readonly", width=24)
        self.quick_project_combo.grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Button(topbar, text="Anlegen", style="Accent.TButton", command=self.quick_add_task).grid(row=0, column=3, sticky="w")
        ttk.Label(topbar, text="Theme").grid(row=0, column=4, sticky="e", padx=(20, 8))
        ttk.Combobox(topbar, textvariable=self.theme_var, state="readonly", values=["Hell", "Dunkel"], width=10).grid(row=0, column=5, sticky="e")
        # Build user label with role badge
        role_badge = f" [{self.current_user.get('role', 'reader').upper()}]"
        self.user_label = ttk.Label(topbar, text=f"Angemeldet: {self.current_user['name']}{role_badge}", style="Subheader.TLabel")
        self.user_label.grid(row=0, column=6, sticky="e", padx=(20, 0))
        account_button_state = "normal" if self.current_user.get("role", "reader") == "admin" else "disabled"
        ttk.Button(topbar, text="Konten", state=account_button_state, command=self.open_account_admin_dialog).grid(row=0, column=7, sticky="e", padx=(12, 0))
        ttk.Button(topbar, text="Mein Konto", command=self.open_account_menu).grid(row=0, column=8, sticky="e", padx=(12, 0))
        ttk.Button(topbar, text="⚙ Auto-Sync", command=self.open_autosync_settings).grid(row=0, column=9, sticky="e", padx=(8, 0))
        ttk.Button(topbar, text="🔄 Sync", command=self.sync_with_server).grid(row=0, column=10, sticky="e", padx=(8, 0))
        ttk.Button(topbar, text="EXE herunterladen", command=self.download_application).grid(row=0, column=11, sticky="e", padx=(8, 0))
        
        # Auto-Sync Status Label (row 1)
        self.autosync_status_var = tk.StringVar(value="Auto-Sync: aus")
        ttk.Label(topbar, textvariable=self.autosync_status_var, foreground="gray").grid(row=1, column=7, columnspan=6, sticky="e", pady=(8, 0))

        ttk.Label(topbar, text="Global suchen").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.global_search_entry = ttk.Entry(topbar, textvariable=self.global_search_var)
        self.global_search_entry.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(8, 8), pady=(8, 0))
        self.global_search_entry.bind("<Return>", self._accept_search_suggestion_or_search)
        self.global_search_entry.bind("<Tab>", self._apply_search_suggestion_text, add="+")
        self.global_search_entry.bind("<KeyRelease>", self._schedule_global_search_suggestions, add="+")
        self.global_search_entry.bind("<Down>", self._select_next_search_suggestion, add="+")
        self.global_search_entry.bind("<Up>", self._select_prev_search_suggestion, add="+")
        self.global_search_entry.bind("<Escape>", self._hide_search_suggestions, add="+")
        self.global_search_entry.bind("<FocusOut>", self._on_global_search_focus_out, add="+")
        ttk.Button(topbar, text="Suchen", command=self.run_global_search).grid(row=1, column=4, sticky="e", pady=(8, 0))
        ttk.Button(topbar, text="Leeren", command=lambda: self.global_search_var.set("")).grid(row=1, column=5, sticky="e", pady=(8, 0))
        ttk.Button(topbar, text="App herunterladen", command=self.download_application).grid(row=1, column=6, sticky="e", padx=(8, 0), pady=(8, 0))
        topbar.columnconfigure(1, weight=1)
        self.theme_var.trace_add("write", lambda *_: self.apply_theme())

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True)

        self.dashboard_tab = ttk.Frame(self.notebook, padding=10)
        self.board_tab = ttk.Frame(self.notebook, padding=10)
        self.tasks_tab = ttk.Frame(self.notebook, padding=10)
        self.projects_tab = ttk.Frame(self.notebook, padding=10)
        self.timeline_tab = ttk.Frame(self.notebook, padding=10)
        self.templates_tab = ttk.Frame(self.notebook, padding=10)
        self.reports_tab = ttk.Frame(self.notebook, padding=10)
        self.backup_tab = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.dashboard_tab, text="Dashboard")
        self.notebook.add(self.board_tab, text="Kanban")
        self.notebook.add(self.tasks_tab, text="Aufgaben")
        self.notebook.add(self.projects_tab, text="Projekte")
        self.notebook.add(self.timeline_tab, text="Zeitstrahl")
        self.notebook.add(self.templates_tab, text="Vorlagen")
        self.notebook.add(self.reports_tab, text="Wochenbericht")
        self.notebook.add(self.backup_tab, text="Backup")

        build_dashboard_tab(self)
        build_board_tab(self)
        build_tasks_tab(self)
        build_projects_tab(self)
        build_timeline_tab(self)
        build_templates_tab(self)
        build_reports_tab(self)
        build_backup_tab(self)
        self._bind_shortcuts()
        self._init_session_timeout()
        self._init_weekly_report_traces()
        self.fill_weekly_report_today()
        self.preview_weekly_report()

    def open_account_admin_dialog(self) -> None:
        if self.current_user.get("role", "reader") != "admin":
            messagebox.showinfo("Konten", "Nur Admin-Accounts können Konten verwalten.", parent=self)
            return
        AccountAdminDialog(self)

    def change_password_dialog(self) -> None:
        """Open dialog to change current user's password."""
        ChangePasswordDialog(self, self.current_user["email"])

    def open_account_menu(self) -> None:
        """Open account management menu."""
        AccountMenuDialog(self, self.current_user["email"], self.relogin)

    def relogin(self) -> None:
        """Open login dialog to switch user."""
        from tkinter import messagebox
        result = messagebox.askyesno(
            "Bestätigung",
            f"Möchtest du dich wirklich als {self.current_user['name']} abmelden?\n\nEs wird automatisch eine Sicherung erstellt."
        )
        if not result:
            return
        
        # Auto-backup before logout (optional feature)
        try:
            if hasattr(self, 'backup_database'):
                self.backup_database()
        except Exception:
            pass  # Backup failure is not critical
        
        dialog = LoginDialog(self)
        self.wait_window(dialog)
        if dialog.current_user:
            # Update current user and principal
            old_user = self.current_user["email"]
            self.current_user = dialog.current_user
            _log_audit_event(old_user, "LOGOUT", "User switched")
            try:
                set_current_principal({"name": self.current_user["email"], "role": self.current_user.get("role", "reader")})
            except Exception:
                pass
            # Update user label with role badge
            role_badge = f" [{self.current_user.get('role', 'reader').upper()}]"
            self.user_label.config(text=f"Angemeldet: {self.current_user['name']}{role_badge}")
            # Refresh UI with new user info
            self.refresh_all()
            messagebox.showinfo("Umgemeldet", f"Angemeldet als: {self.current_user['name']}", parent=self)

    def _local_lan_address(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def _collab_base_url(self) -> str:
        base_url = os.getenv("PM_BASE_URL", "https://100.80.250.84:8765")
        return base_url.rstrip("/")

    def sync_with_server(self) -> None:
        """Synchronize local data with collaboration server."""
        from pmtool.sync import SyncManager
        
        base_url = self._collab_base_url()
        
        # Show progress dialog
        progress = messagebox.showinfo(
            "Synchronisierung",
            "Verbinde zum Server...",
            parent=self,
        )
        
        try:
            # Initialize sync manager
            sync_manager = SyncManager(base_url)
            
            # Prepare data to upload
            projects = [dict(row) for row in list_projects()]
            tasks = [dict(row) for row in list_tasks(include_done=True)]
            milestones = [dict(row) for row in list_milestones()]
            templates = [dict(row) for row in list_templates()]
            
            # Upload to server
            result = sync_manager.sync_to_server(
                projects=projects,
                tasks=tasks,
                milestones=milestones,
                templates=templates,
            )
            
            # Handle results
            if result.get("status") == "offline":
                messagebox.showwarning(
                    "Verbindungsfehler",
                    f"Kann nicht zum Server verbinden:\n{result.get('error')}",
                    parent=self,
                )
                return
            
            conflicts = result.get("conflicts", [])
            if conflicts:
                conflict_msg = "Synchronisierung mit Konflikten abgeschlossen:\n\n"
                for conflict in conflicts[:5]:  # Show first 5 conflicts
                    conflict_msg += f"- {conflict['type']} #{conflict['id']}: {conflict['error']}\n"
                if len(conflicts) > 5:
                    conflict_msg += f"\n... und {len(conflicts) - 5} weitere Konflikte"
                messagebox.showwarning(
                    "Synchronisierung - Konflikte",
                    conflict_msg,
                    parent=self,
                )
            else:
                messagebox.showinfo(
                    "Synchronisierung erfolgreich",
                    f"✓ {len(projects)} Projekte\n"
                    f"✓ {len(tasks)} Aufgaben\n"
                    f"✓ {len(milestones)} Meilensteine\n"
                    f"✓ {len(templates)} Vorlagen\n\n"
                    "wurden mit dem Server synchronisiert.",
                    parent=self,
                )
                self.refresh_all()
        
        except Exception as e:
            messagebox.showerror(
                "Synchronisierungsfehler",
                f"Fehler bei der Synchronisierung:\n{str(e)}",
                parent=self,
            )

    def open_autosync_settings(self) -> None:
        """Open Auto-Sync settings dialog."""
        from pmtool.sync import SyncManager, AutoSyncManager
        
        base_url = self._collab_base_url()
        
        # Create settings dialog
        dialog = tk.Toplevel(self)
        dialog.title("Auto-Sync Einstellungen")
        dialog.geometry("400x250")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        
        ttk.Label(frame, text="Auto-Synchronisierung", style="Header.TLabel").pack(anchor="w", pady=(0, 12))
        
        # Enable/Disable
        enabled_var = tk.BooleanVar(value=getattr(self, "_autosync_enabled", False))
        ttk.Checkbutton(
            frame,
            text="Auto-Sync aktivieren",
            variable=enabled_var,
        ).pack(anchor="w", pady=(0, 12))
        
        # Interval selection
        ttk.Label(frame, text="Synchronisierungsintervall:").pack(anchor="w", pady=(0, 4))
        interval_var = tk.StringVar(value=str(getattr(self, "_autosync_interval", 300)))
        interval_frame = ttk.Frame(frame)
        interval_frame.pack(fill="x", pady=(0, 12))
        ttk.Combobox(
            interval_frame,
            textvariable=interval_var,
            values=["60", "300", "600", "900", "1800"],
            state="readonly",
            width=15,
        ).pack(side="left", padx=(0, 8))
        ttk.Label(interval_frame, text="Sekunden").pack(side="left")
        
        # Labels for common intervals
        ttk.Label(frame, text="(1 Min = 60s, 5 Min = 300s, 10 Min = 600s)", foreground="gray", font=("TkDefaultFont", 8)).pack(anchor="w", pady=(0, 12))
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill="x")
        
        def on_apply() -> None:
            """Apply auto-sync settings."""
            try:
                interval = int(interval_var.get())
                
                # Store settings
                self._autosync_enabled = enabled_var.get()
                self._autosync_interval = interval
                
                # Initialize or update AutoSyncManager
                if enabled_var.get():
                    if not hasattr(self, "_autosync_manager"):
                        sync_manager = SyncManager(base_url)
                        self._autosync_manager = AutoSyncManager(
                            sync_manager,
                            interval_seconds=interval,
                            enabled=True,
                            on_sync_callback=self._on_autosync_complete,
                        )
                    else:
                        self._autosync_manager.set_interval(interval)
                        self._autosync_manager.set_enabled(True)
                    
                    self.autosync_status_var.set(f"Auto-Sync: alle {interval}s")
                    messagebox.showinfo(
                        "Auto-Sync aktiviert",
                        f"Auto-Sync ist aktiviert.\n\nSynchronisierungsintervall: {interval} Sekunden",
                        parent=dialog,
                    )
                else:
                    if hasattr(self, "_autosync_manager"):
                        self._autosync_manager.set_enabled(False)
                    
                    self.autosync_status_var.set("Auto-Sync: aus")
                    messagebox.showinfo(
                        "Auto-Sync deaktiviert",
                        "Auto-Sync ist deaktiviert.",
                        parent=dialog,
                    )
                
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Fehler", "Ungültiges Intervall", parent=dialog)
        
        ttk.Button(button_frame, text="Übernehmen", style="Accent.TButton", command=on_apply).pack(side="left", padx=(0, 6))
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side="left")

    def _on_autosync_complete(self, result: dict[str, Any]) -> None:
        """Callback when auto-sync completes.
        
        Args:
            result: Result dictionary from sync operation
        """
        # Silently update status
        if result.get("status") == "offline":
            pass  # Don't bother user with offline messages during auto-sync
        else:
            # Update view if data changed
            try:
                self.refresh_all()
            except Exception:
                pass  # Ignore refresh errors in background

    def download_application(self) -> None:
        download_url = f"{self._collab_base_url()}/download/exe"
        webbrowser.open(download_url)
        messagebox.showinfo(
            "App herunterladen",
            "Der Download wurde im Browser geöffnet. Dort kannst du die Datei speichern.",
            parent=self,
        )

    def apply_theme(self) -> None:
        palette = self._palette()
        self.configure(bg=palette["bg"])
        for widget in self.winfo_children():
            try:
                # Only apply style to ttk widgets
                if hasattr(widget, 'configure') and 'style' in widget.keys():
                    widget.configure(style="Root.TFrame")
            except (tk.TclError, AttributeError, TypeError):
                pass
        self.style.configure("Root.TFrame", background=palette["bg"])
        self.style.configure("TFrame", background=palette["bg"])
        self.style.configure("TLabel", background=palette["bg"], foreground=palette["text"], font=("Segoe UI", 10))
        self.style.configure("Header.TLabel", background=palette["bg"], foreground=palette["title"], font=("Segoe UI Semibold", 20))
        self.style.configure("Subheader.TLabel", background=palette["bg"], foreground=palette["muted"], font=("Segoe UI", 10))
        self.style.configure("Card.TFrame", background=palette["card"], relief="flat")
        self.style.configure("CardTitle.TLabel", background=palette["card"], foreground=palette["muted"], font=("Segoe UI", 9))
        self.style.configure("CardValue.TLabel", background=palette["card"], foreground=palette["title"], font=("Segoe UI Semibold", 18))
        self.style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), foreground=palette["button_text"], background=palette["accent"])
        self.style.map("Accent.TButton", background=[("active", palette["accent_hover"])])
        self.style.configure("Treeview", background=palette["tree_bg"], fieldbackground=palette["tree_bg"], foreground=palette["text"], rowheight=26)
        self.style.configure("Treeview.Heading", background=palette["card"], foreground=palette["text"], font=("Segoe UI Semibold", 9))
        self.style.configure("TNotebook", background=palette["bg"])
        self.style.configure("TNotebook.Tab", padding=(12, 6))
        for text_widget in getattr(self, "text_widgets", []):
            text_widget.configure(bg=palette["text_bg"], fg=palette["text"], insertbackground=palette["text"])
        for listbox in getattr(self, "listboxes", []):
            listbox.configure(bg=palette["text_bg"], fg=palette["text"], selectbackground=palette["accent"], selectforeground=palette["button_text"])
        if hasattr(self, "timeline_canvas"):
            self.refresh_timeline()

    def _palette(self) -> dict[str, str]:
        if self.theme_var.get() == "Dunkel":
            return {
                "bg": "#1f2933",
                "card": "#27323f",
                "title": "#f8fafc",
                "text": "#e5e7eb",
                "muted": "#aab4c0",
                "accent": "#0f766e",
                "accent_hover": "#115e59",
                "button_text": "#f8fafc",
                "tree_bg": "#22303d",
                "text_bg": "#22303d",
            }
        return {
            "bg": "#f4f1ea",
            "card": "#ffffff",
            "title": "#102a43",
            "text": "#1f2933",
            "muted": "#52606d",
            "accent": "#0b7285",
            "accent_hover": "#075985",
            "button_text": "#ffffff",
            "tree_bg": "#ffffff",
            "text_bg": "#ffffff",
        }

    def _make_card(self, parent: ttk.Frame, title: str, key: str) -> ttk.Label:
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
        value = ttk.Label(card, text="0", style="CardValue.TLabel")
        value.pack(anchor="w", pady=(6, 0))
        setattr(self, key, value)
        return value

    def refresh_all(self) -> None:
        """Refresh all UI components."""
        self.refresh_project_combo_boxes()
        self.refresh_dashboard()
        self.refresh_board()
        self.refresh_projects()
        self.refresh_tasks()
        self.refresh_timeline()
        self.refresh_templates()

    def refresh_project_combo_boxes(self) -> None:
        project_labels = ["Keine Zuordnung"] + [f'{project["id"]}: {project["name"]}' for project in list_projects()]
        self.quick_project_combo["values"] = project_labels
        self.project_filter_combo["values"] = ["Alle Projekte"] + [f'{project["id"]}: {project["name"]}' for project in list_projects()]
        if hasattr(self, "timeline_project_combo"):
            timeline_labels = ["Projekt wählen"] + [f'{project["id"]}: {project["name"]}' for project in list_projects()]
            self.timeline_project_combo["values"] = timeline_labels
            if self.timeline_project_var.get() not in timeline_labels:
                self.timeline_project_var.set("Projekt wählen")
        if hasattr(self, "report_project_combo"):
            report_labels = ["Projekt wählen"] + [f'{project["id"]}: {project["name"]}' for project in list_projects()]
            self.report_project_combo["values"] = report_labels
            if self.report_project_var.get() not in report_labels:
                self.report_project_var.set("Projekt wählen")
            self.load_report_project_tasks(silent=True)
        if self.quick_project_var.get() not in project_labels:
            self.quick_project_var.set("Keine Zuordnung")
        if self.project_filter_var.get() not in self.project_filter_combo["values"]:
            self.project_filter_var.set("Alle Projekte")

    def selected_project_id(self) -> int | None:
        """Get the currently selected project ID from filter dropdown."""
        return id_from_labeled_value(self.project_filter_var.get(), "Alle Projekte")

    def refresh_dashboard(self) -> None:
        """Refresh the dashboard tab."""
        tabs_refresh_dashboard(self)

    def refresh_board(self) -> None:
        """Refresh the Kanban board tab."""
        tabs_refresh_board(self)

    def refresh_projects(self) -> None:
        """Refresh the projects tab."""
        tabs_refresh_projects(self)

    def refresh_tasks(self) -> None:
        """Refresh the tasks tab."""
        tabs_refresh_tasks(self)

    def refresh_templates(self) -> None:
        """Refresh the templates tab."""
        tabs_refresh_templates(self)

    def refresh_timeline(self) -> None:
        """Refresh the timeline tab."""
        tabs_refresh_timeline(self)

    def update_project_milestones(self) -> None:
        tabs_update_project_milestones(self)

    def update_task_details(self) -> None:
        tabs_update_task_details(self)

    def update_active_template(self) -> None:
        tabs_update_active_template(self)

    def update_active_milestone(self) -> None:
        tabs_update_active_milestone(self)

    def selected_task_id(self) -> int | None:
        """Get the currently selected task ID."""
        return tabs_selected_task_id(self)

    def selected_project_tree_id(self) -> int | None:
        """Get the currently selected project ID from tree view."""
        return tabs_selected_project_tree_id(self)

    def selected_template_id(self) -> int | None:
        """Get the currently selected template ID."""
        return tabs_selected_template_id(self)

    def selected_milestone_id(self) -> int | None:
        """Get the currently selected milestone ID."""
        return tabs_selected_milestone_id(self)

    def open_project_in_tasks_tab(self) -> None:
        """Open selected project in tasks tab."""
        tabs_open_project_in_tasks_tab(self)

    def open_selected_project_task(self) -> None:
        """Open selected project task."""
        tabs_open_selected_project_task(self)

    def open_selected_project_template(self) -> None:
        """Open selected project template."""
        tabs_open_selected_project_template(self)

    def show_selected_project_shares(self) -> None:
        project_id = self.selected_project_tree_id()
        if project_id is None:
            messagebox.showinfo("Freigaben", "Bitte zuerst ein Projekt auswählen.", parent=self)
            return
        try:
            shares = list_project_shares(project_id)
        except ValueError as exc:
            messagebox.showerror("Freigaben", str(exc), parent=self)
            return
        if not shares:
            messagebox.showinfo("Freigaben", "Für dieses Projekt gibt es keine Freigaben.", parent=self)
            return
        lines = [str(row["account_name"]) for row in shares]
        messagebox.showinfo("Freigaben", "\n".join(lines), parent=self)

    def share_selected_project(self) -> None:
        project_id = self.selected_project_tree_id()
        if project_id is None:
            messagebox.showinfo("Freigaben", "Bitte zuerst ein Projekt auswählen.", parent=self)
            return
        
        dialog = EmailSharingDialog(self, "Projekt teilen - E-Mail auswählen")
        self.wait_window(dialog)
        
        if dialog.result is None:
            return
        
        try:
            share_project(project_id, dialog.result)
        except ValueError as exc:
            messagebox.showerror("Freigaben", str(exc), parent=self)
            return
        self.refresh_projects()
        messagebox.showinfo("Freigaben", f"Projekt freigegeben für: {dialog.result}", parent=self)

    def unshare_selected_project(self) -> None:
        project_id = self.selected_project_tree_id()
        if project_id is None:
            messagebox.showinfo("Freigaben", "Bitte zuerst ein Projekt auswählen.", parent=self)
            return
        
        dialog = EmailSharingDialog(self, "Freigabe entfernen - E-Mail auswählen")
        self.wait_window(dialog)
        
        if dialog.result is None:
            return
        
        try:
            unshare_project(project_id, dialog.result)
        except ValueError as exc:
            messagebox.showerror("Freigaben", str(exc), parent=self)
            return
        self.refresh_projects()
        messagebox.showinfo("Freigaben", f"Freigabe entfernt für: {dialog.result}", parent=self)
        self.refresh_projects()

    def _status_filter_value(self) -> str | None:
        """Get the current status filter value."""
        return status_filter_value(self)

    def _energy_filter_value(self) -> str | None:
        """Get the current energy filter value."""
        return energy_filter_value(self)

    def _due_filter_value(self) -> str | None:
        """Get the current due date filter value."""
        return due_filter_value(self)

    def quick_add_task(self) -> None:
        """Quickly add a new task from the topbar input."""
        title = self.quick_title_var.get().strip()
        if not title:
            messagebox.showerror("Fehler", "Der Titel darf nicht leer sein.", parent=self)
            return
        project_id = id_from_labeled_value(self.quick_project_var.get(), "Keine Zuordnung")
        try:
            add_task(title, project_id=project_id)
        except ValueError as exc:
            messagebox.showerror("Fehler", str(exc), parent=self)
            return
        self.quick_title_var.set("")
        self.refresh_all()

    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-n>", lambda event: self._shortcut_action(event, self.add_task_dialog))
        self.bind_all("<Control-Shift-N>", lambda event: self._shortcut_action(event, self.add_project_dialog))
        self.bind_all("<Control-e>", lambda event: self._shortcut_action(event, self.edit_selected_task))
        self.bind_all("<Control-d>", lambda event: self._shortcut_action(event, self.duplicate_selected_task))
        self.bind_all("<Delete>", lambda event: self._shortcut_action(event, self.delete_selected_task))
        self.bind_all("<F5>", lambda _: self.refresh_all())
        self.bind_all("<Control-f>", lambda _: self.focus_search())
        self.bind_all("<Control-k>", lambda _: self.focus_global_search())
        self.bind_all("<Control-u>", lambda _: self.relogin())
        self.bind_all("<Control-1>", lambda _: self.notebook.select(self.dashboard_tab))
        self.bind_all("<Control-2>", lambda _: self.notebook.select(self.board_tab))
        # Reset session timeout on any user activity
        self.bind_all("<Motion>", lambda _: self._reset_session_timeout())
        self.bind_all("<Button>", lambda _: self._reset_session_timeout())
        self.bind_all("<Key>", lambda _: self._reset_session_timeout())
    
    def _init_session_timeout(self) -> None:
        """Initialize session timeout checking."""
        self._reset_session_timeout()
    
    def _reset_session_timeout(self) -> None:
        """Reset the session timeout counter on user activity."""
        if self.session_timeout_id is not None:
            self.after_cancel(self.session_timeout_id)
        self.session_idle_seconds = 0
        # Check timeout every 5 seconds
        self.session_timeout_id = self.after(5000, self._check_session_timeout)
    
    def _check_session_timeout(self) -> None:
        """Check if session timeout is reached."""
        self.session_idle_seconds += 5
        
        # 1 minute warning (1740 seconds into 30 min timeout)
        if self.session_idle_seconds == 1740:
            from tkinter import messagebox
            messagebox.showwarning(
                "Session läuft ab",
                f"Deine Sitzung läuft in 1 Minute ab (inaktiv seit {self.session_idle_seconds // 60} Minuten).\n\n"
                "Klicke auf OK, um die Sitzung zu verlängern.",
                parent=self
            )
            # Reset on response
            self._reset_session_timeout()
        # Timeout reached
        elif self.session_idle_seconds >= self.session_timeout_seconds:
            from tkinter import messagebox
            messagebox.showinfo(
                "Session beendet",
                "Deine Sitzung ist abgelaufen. Du wirst jetzt abgemeldet.",
                parent=self
            )
            self.relogin()
        else:
            # Keep checking
            self.session_timeout_id = self.after(5000, self._check_session_timeout)
        self.bind_all("<Control-3>", lambda _: self.notebook.select(self.tasks_tab))
        self.bind_all("<Control-4>", lambda _: self.notebook.select(self.projects_tab))
        self.bind_all("<Control-5>", lambda _: self.notebook.select(self.timeline_tab))
        self.bind_all("<Control-6>", lambda _: self.notebook.select(self.templates_tab))
        self.bind_all("<Control-7>", lambda _: self.notebook.select(self.reports_tab))
        self.bind_all("<Control-8>", lambda _: self.notebook.select(self.backup_tab))

    def _shortcut_action(self, event: tk.Event, action) -> str:
        focused_widget = self.focus_get()
        if focused_widget is not None:
            widget_class = focused_widget.winfo_class()
            if widget_class in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}:
                return "break"
        action()
        return "break"

    def focus_search(self) -> None:
        self.notebook.select(self.tasks_tab)
        self.update_idletasks()
        self.search_entry.focus_set()

    def focus_global_search(self) -> None:
        self.update_idletasks()
        self.global_search_entry.focus_set()
        self.global_search_entry.selection_range(0, tk.END)

    def _on_global_search_focus_out(self, _event=None) -> None:
        self.after(120, self._hide_search_suggestions_if_unfocused)

    def _hide_search_suggestions_if_unfocused(self) -> None:
        focused = self.focus_get()
        if focused is self._search_suggest_listbox:
            return
        self._hide_search_suggestions()

    def _schedule_global_search_suggestions(self, _event=None) -> None:
        if self._search_suggest_after_id is not None:
            try:
                self.after_cancel(self._search_suggest_after_id)
            except tk.TclError:
                pass
        self._search_suggest_after_id = self.after(160, self._update_global_search_suggestions)

    def _update_global_search_suggestions(self) -> None:
        self._search_suggest_after_id = None
        query = self.global_search_var.get().strip()
        if not query:
            self._hide_search_suggestions()
            return
        results = self._collect_global_search_results(query)
        suggestions = results[: self._search_suggest_max]
        self._search_suggest_results = self._build_search_suggestion_items(suggestions)
        if not self._search_suggest_results:
            self._hide_search_suggestions()
            return
        self._show_search_suggestions()

    def _build_search_suggestion_items(self, suggestions: list[dict[str, object]]) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        items.append({
            "kind": "Hinweis",
            "title": "Enter = oeffnen | Tab = uebernehmen | Esc = schliessen",
            "subtitle": "",
            "selectable": False,
        })
        priority = ["Aufgabe", "Projekt", "Vorlage", "Meilenstein", "Notiz", "Verlauf", "Funktion"]
        kinds = [str(item.get("kind", "")) for item in suggestions]
        ordered_kinds = [kind for kind in priority if kind in kinds]
        for kind in kinds:
            if kind and kind not in ordered_kinds:
                ordered_kinds.append(kind)
        for kind in ordered_kinds:
            items.append({"kind": kind, "title": f"== {kind} ==", "subtitle": "", "selectable": False})
            items.extend([item for item in suggestions if str(item.get("kind", "")) == kind])
        return items

    def _format_search_suggestion(self, item: dict[str, object]) -> str:
        if not item.get("selectable", True):
            return f"{item.get('title', '')}"
        kind = str(item.get("kind", ""))
        prefixes = {
            "Aufgabe": "TASK",
            "Projekt": "PROJ",
            "Vorlage": "TPL",
            "Meilenstein": "MS",
            "Notiz": "NOTE",
            "Verlauf": "HIST",
            "Funktion": "CMD",
        }
        prefix = prefixes.get(kind, "ITEM")
        preview = _truncate_preview(item.get("preview", ""), self._search_suggest_preview_limit)
        suffix = f" | {preview}" if preview else ""
        return f"{prefix}: {item['title']} - {item['subtitle']}{suffix}"

    def _is_selectable_suggestion(self, item: dict[str, object]) -> bool:
        return bool(item.get("selectable", True))

    def _find_next_selectable_index(self, start_index: int) -> int | None:
        for idx in range(start_index, len(self._search_suggest_results)):
            if self._is_selectable_suggestion(self._search_suggest_results[idx]):
                return idx
        return None

    def _find_prev_selectable_index(self, start_index: int) -> int | None:
        for idx in range(start_index, -1, -1):
            if self._is_selectable_suggestion(self._search_suggest_results[idx]):
                return idx
        return None

    def _show_search_suggestions(self) -> None:
        if self._search_suggest_popup is None or not self._search_suggest_popup.winfo_exists():
            popup = tk.Toplevel(self)
            popup.overrideredirect(True)
            popup.attributes("-topmost", True)
            popup.transient(self)
            listbox = tk.Listbox(popup, activestyle="dotbox")
            listbox.pack(fill="both", expand=True)
            listbox.bind("<ButtonRelease-1>", self._accept_search_suggestion)
            listbox.bind("<Return>", self._accept_search_suggestion)
            listbox.bind("<Escape>", self._hide_search_suggestions)
            listbox.bind("<FocusOut>", lambda _e: self._hide_search_suggestions())
            listbox.bind("<Motion>", self._on_search_suggestion_motion)
            listbox.bind("<Leave>", lambda _e: None)
            self._search_suggest_popup = popup
            self._search_suggest_listbox = listbox
            if not hasattr(self, "listboxes"):
                self.listboxes = []
            self.listboxes.append(listbox)
            self.apply_theme()

        assert self._search_suggest_listbox is not None
        listbox = self._search_suggest_listbox
        listbox.delete(0, tk.END)
        palette = self._palette()
        for item in self._search_suggest_results:
            listbox.insert(tk.END, self._format_search_suggestion(item))
            if not self._is_selectable_suggestion(item):
                listbox.itemconfig(tk.END, foreground=palette["muted"], background=palette["text_bg"])

        visible_count = max(1, len(self._search_suggest_results))
        listbox.configure(height=visible_count)
        first_selectable = self._find_next_selectable_index(0)
        if first_selectable is not None:
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(first_selectable)
            listbox.see(first_selectable)
        self._position_search_suggestions()

    def _position_search_suggestions(self) -> None:
        if self._search_suggest_popup is None or self._search_suggest_listbox is None:
            return
        self.update_idletasks()
        entry = self.global_search_entry
        x = entry.winfo_rootx()
        y = entry.winfo_rooty() + entry.winfo_height()
        width = entry.winfo_width()
        row_height = max(22, self._search_suggest_listbox.winfo_reqheight() // max(1, self._search_suggest_listbox.size()))
        height = min(240, row_height * max(1, self._search_suggest_listbox.size()) + 6)
        self._search_suggest_popup.geometry(f"{width}x{height}+{x}+{y}")

    def _hide_search_suggestions(self, _event=None) -> None:
        if self._search_suggest_popup is not None and self._search_suggest_popup.winfo_exists():
            self._search_suggest_popup.destroy()
        self._search_suggest_popup = None
        self._search_suggest_listbox = None
        self._search_suggest_results = []

    def _accept_search_suggestion_or_search(self, _event=None) -> str | None:
        if self._search_suggest_listbox is not None and self._search_suggest_listbox.size() > 0:
            selection = self._search_suggest_listbox.curselection()
            if selection:
                if self._accept_search_suggestion():
                    return "break"
        self._hide_search_suggestions()
        self.run_global_search()
        return "break"

    def _on_search_suggestion_motion(self, event) -> None:
        if self._search_suggest_listbox is None:
            return
        index = self._search_suggest_listbox.nearest(event.y)
        if index < 0 or index >= len(self._search_suggest_results):
            return
        if not self._is_selectable_suggestion(self._search_suggest_results[index]):
            next_index = self._find_next_selectable_index(index + 1)
            if next_index is None:
                prev_index = self._find_prev_selectable_index(index - 1)
                if prev_index is None:
                    return
                index = prev_index
            else:
                index = next_index
        self._search_suggest_listbox.selection_clear(0, tk.END)
        self._search_suggest_listbox.selection_set(index)
        self._search_suggest_listbox.see(index)

    def _accept_search_suggestion(self, _event=None) -> bool:
        if self._search_suggest_listbox is None:
            return False
        selection = self._search_suggest_listbox.curselection()
        if not selection:
            return False
        index = int(selection[0])
        if index < 0 or index >= len(self._search_suggest_results):
            return False
        if not self._is_selectable_suggestion(self._search_suggest_results[index]):
            next_index = self._find_next_selectable_index(index + 1)
            if next_index is None:
                return False
            index = next_index
        item = self._search_suggest_results[index]
        self._hide_search_suggestions()
        self._execute_global_search_result(item)
        return True

    def _apply_search_suggestion_text(self, _event=None) -> str | None:
        if self._search_suggest_listbox is None:
            return "break"
        selection = self._search_suggest_listbox.curselection()
        if not selection:
            return "break"
        index = int(selection[0])
        if index < 0 or index >= len(self._search_suggest_results):
            return "break"
        item = self._search_suggest_results[index]
        if not self._is_selectable_suggestion(item):
            next_index = self._find_next_selectable_index(index + 1)
            if next_index is None:
                return "break"
            item = self._search_suggest_results[next_index]
        title = str(item.get("title", "")).strip()
        if title:
            self.global_search_var.set(title)
            self.global_search_entry.icursor(tk.END)
            self.global_search_entry.selection_range(0, tk.END)
            self._schedule_global_search_suggestions()
        return "break"

    def _select_next_search_suggestion(self, _event=None) -> str | None:
        if self._search_suggest_listbox is None:
            return None
        size = self._search_suggest_listbox.size()
        if size == 0:
            return None
        selection = self._search_suggest_listbox.curselection()
        start_index = (selection[0] + 1) if selection else 0
        next_index = self._find_next_selectable_index(start_index)
        if next_index is None:
            return "break"
        index = next_index
        self._search_suggest_listbox.selection_clear(0, tk.END)
        self._search_suggest_listbox.selection_set(index)
        self._search_suggest_listbox.see(index)
        return "break"

    def _select_prev_search_suggestion(self, _event=None) -> str | None:
        if self._search_suggest_listbox is None:
            return None
        size = self._search_suggest_listbox.size()
        if size == 0:
            return None
        selection = self._search_suggest_listbox.curselection()
        start_index = (selection[0] - 1) if selection else 0
        prev_index = self._find_prev_selectable_index(start_index)
        if prev_index is None:
            return "break"
        index = prev_index
        self._search_suggest_listbox.selection_clear(0, tk.END)
        self._search_suggest_listbox.selection_set(index)
        self._search_suggest_listbox.see(index)
        return "break"

    def run_global_search(self) -> None:
        self._hide_search_suggestions()
        query = self.global_search_var.get().strip()
        if not query:
            self.focus_global_search()
            return

        results = self._collect_global_search_results(query)
        if not results:
            messagebox.showinfo("Suche", f"Keine Treffer für '{query}'.", parent=self)
            return

        if len(results) == 1:
            self._execute_global_search_result(results[0])
            return

        self._show_global_search_results(query, results)

    def _collect_global_search_results(self, query: str) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []

        function_items = [
            ("Funktion", "Dashboard öffnen", ["dashboard", "übersicht"], lambda: self.notebook.select(self.dashboard_tab)),
            ("Funktion", "Kanban öffnen", ["kanban", "board"], lambda: self.notebook.select(self.board_tab)),
            ("Funktion", "Aufgaben öffnen", ["aufgaben", "tasks"], lambda: self.notebook.select(self.tasks_tab)),
            ("Funktion", "Projekte öffnen", ["projekte", "projects"], lambda: self.notebook.select(self.projects_tab)),
            ("Funktion", "Zeitstrahl öffnen", ["zeitstrahl", "timeline"], lambda: self.notebook.select(self.timeline_tab)),
            ("Funktion", "Vorlagen öffnen", ["vorlagen", "templates"], lambda: self.notebook.select(self.templates_tab)),
            ("Funktion", "Wochenbericht öffnen", ["wochenbericht", "report"], lambda: self.notebook.select(self.reports_tab)),
            ("Funktion", "Backup öffnen", ["backup", "import", "export"], lambda: self.notebook.select(self.backup_tab)),
            ("Funktion", "Neue Aufgabe", ["neu", "aufgabe", "task"], self.add_task_dialog),
            ("Funktion", "Neues Projekt", ["neu", "projekt"], self.add_project_dialog),
            ("Funktion", "Suche in Aufgaben fokussieren", ["suche", "filter", "find"], self.focus_search),
            ("Funktion", "Alles aktualisieren", ["refresh", "aktualisieren", "neu laden"], self.refresh_all),
        ]

        for index, (kind, title, keywords, action) in enumerate(function_items):
            score = _match_score(query, title, *keywords)
            if score:
                results.append({
                    "kind": kind,
                    "title": title,
                    "subtitle": "Befehl",
                    "action": action,
                    "score": score,
                    "order": index,
                })

        for index, project_row in enumerate(list_projects()):
            project = dict(project_row)
            project_name = str(project.get("name", "")).strip()
            project_status = str(project.get("status", ""))
            project_goal = str(project.get("goal", ""))
            project_description = str(project.get("description", "") or "")
            score = _match_score(query, project_name, project_status, project_goal, project_description)
            if score:
                results.append(
                    {
                        "kind": "Projekt",
                        "title": project_name or "(Ohne Name)",
                        "subtitle": f"ID {project['id']} | Status: {project_status or '-'}",
                        "project_id": int(project["id"]),
                        "score": score,
                        "order": index,
                    }
                )

        tasks = list_tasks(include_done=True)
        for index, task_row in enumerate(tasks):
            task = dict(task_row)
            task_title = str(task.get("title", "")).strip()
            task_status = str(task.get("status", ""))
            task_project = str(task.get("project_name", "") or "-")
            task_tags = str(task.get("tags", "") or "")
            task_details = str(task.get("details", "") or "")
            task_context = str(task.get("context", "") or "")
            task_blocker = str(task.get("blocked_reason", "") or "")
            score = _match_score(
                query,
                task_title,
                task_status,
                task_project,
                task_tags,
                task_details,
                task_context,
                task_blocker,
            )
            if score:
                results.append(
                    {
                        "kind": "Aufgabe",
                        "title": task_title or "(Ohne Titel)",
                        "subtitle": f"ID {task['id']} | {task_project} | {task_status}",
                        "task_id": int(task["id"]),
                        "project_id": task.get("project_id"),
                        "score": score,
                        "order": index,
                    }
                )

        for index, template_row in enumerate(list_templates()):
            template = dict(template_row)
            template_title = str(template.get("title", "")).strip()
            template_name = str(template.get("name", "")).strip()
            template_details = str(template.get("details", "") or "")
            template_tags = str(template.get("tags", "") or "")
            template_context = str(template.get("context", "") or "")
            template_status = str(template.get("status", ""))
            score = _match_score(
                query,
                template_title or template_name,
                template_name,
                template_details,
                template_tags,
                template_context,
                template_status,
            )
            if score:
                results.append(
                    {
                        "kind": "Vorlage",
                        "title": template_title or "(Ohne Titel)",
                        "subtitle": f"{template_name or 'Ohne Name'} | {template_status}",
                        "template_id": int(template["id"]),
                        "preview": _truncate_preview(template_details),
                        "score": score,
                        "order": index,
                    }
                )

        for index, milestone_row in enumerate(list_milestones()):
            milestone = dict(milestone_row)
            milestone_title = str(milestone.get("title", "")).strip()
            milestone_status = str(milestone.get("status", ""))
            milestone_project = str(milestone.get("project_name", "") or "-")
            milestone_due = str(milestone.get("due_date", "") or "-")
            score = _match_score(query, milestone_title, milestone_status, milestone_project, milestone_due)
            if score:
                results.append(
                    {
                        "kind": "Meilenstein",
                        "title": milestone_title or "(Ohne Titel)",
                        "subtitle": f"{milestone_project} | {milestone_due} | {milestone_status}",
                        "milestone_id": int(milestone["id"]),
                        "project_id": milestone.get("project_id"),
                        "score": score,
                        "order": index,
                    }
                )

        for index, task_row in enumerate(tasks):
            task = dict(task_row)
            task_id = int(task["id"])
            for note_row in list_task_notes(task_id):
                note = dict(note_row)
                note_text = str(note.get("note", "") or "")
                score = _match_score(query, task.get("title", ""), note_text)
                if score:
                    results.append(
                        {
                            "kind": "Notiz",
                            "title": task.get("title", "(Ohne Titel)"),
                            "subtitle": f"ID {task_id} | {task.get('project_name', '-')}",
                            "task_id": task_id,
                            "project_id": task.get("project_id"),
                            "preview": _truncate_preview(note_text),
                            "score": score,
                            "order": index,
                        }
                    )
            for history_row in list_task_history(task_id):
                history = dict(history_row)
                history_action = str(history.get("action", "") or "")
                history_details = str(history.get("details", "") or "")
                score = _match_score(query, task.get("title", ""), history_action, history_details)
                if score:
                    results.append(
                        {
                            "kind": "Verlauf",
                            "title": task.get("title", "(Ohne Titel)"),
                            "subtitle": f"ID {task_id} | {history_action}",
                            "task_id": task_id,
                            "project_id": task.get("project_id"),
                            "preview": _truncate_preview(history_details),
                            "score": score,
                            "order": index,
                        }
                    )

        results.sort(key=lambda item: (-int(item.get("score", 0)), int(item.get("order", 0))))
        return results[:200]

    def _show_global_search_results(self, query: str, results: list[dict[str, object]]) -> None:
        popup = tk.Toplevel(self)
        popup.title(f"Suche: {query}")
        popup.geometry("860x520")
        popup.transient(self)

        host = ttk.Frame(popup, padding=10)
        host.pack(fill="both", expand=True)

        ttk.Label(host, text=f"{len(results)} Treffer", style="Subheader.TLabel").pack(anchor="w")

        list_frame = ttk.Frame(host)
        list_frame.pack(fill="both", expand=True, pady=(8, 0))

        result_list = tk.Listbox(list_frame, activestyle="dotbox")
        result_list.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=result_list.yview)
        scroll.pack(side="right", fill="y")
        result_list.configure(yscrollcommand=scroll.set)

        for item in results:
            preview = _truncate_preview(item.get("preview", ""))
            suffix = f" | {preview}" if preview else ""
            result_list.insert(tk.END, f"[{item['kind']}] {item['title']} - {item['subtitle']}{suffix}")

        def run_selected(_event=None):
            selection = result_list.curselection()
            if not selection:
                return
            index = int(selection[0])
            if index < 0 or index >= len(results):
                return
            self._execute_global_search_result(results[index])
            popup.destroy()

        result_list.bind("<Double-Button-1>", run_selected)
        result_list.bind("<Return>", run_selected)

        buttons = ttk.Frame(host)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Öffnen", command=run_selected).pack(side="left")
        ttk.Button(buttons, text="Schließen", command=popup.destroy).pack(side="right")

        result_list.focus_set()
        if results:
            result_list.selection_set(0)

    def _execute_global_search_result(self, item: dict[str, object]) -> None:
        kind = str(item.get("kind", ""))
        if kind == "Funktion":
            action = item.get("action")
            if callable(action):
                action()
            return

        if kind == "Projekt":
            project_id = item.get("project_id")
            if isinstance(project_id, int):
                self._open_project_from_global_search(project_id)
            return

        if kind == "Aufgabe":
            task_id = item.get("task_id")
            if isinstance(task_id, int):
                self._open_task_from_global_search(task_id)
            return

        if kind in {"Notiz", "Verlauf"}:
            task_id = item.get("task_id")
            if isinstance(task_id, int):
                self._open_task_from_global_search(task_id)
            return

        if kind == "Vorlage":
            template_id = item.get("template_id")
            if isinstance(template_id, int):
                self._open_template_from_global_search(template_id)
            return

        if kind == "Meilenstein":
            milestone_id = item.get("milestone_id")
            project_id = item.get("project_id")
            if isinstance(milestone_id, int) and isinstance(project_id, int):
                self._open_milestone_from_global_search(project_id, milestone_id)
            return

    def _open_project_from_global_search(self, project_id: int) -> None:
        self.notebook.select(self.projects_tab)
        self.refresh_projects()
        iid = str(project_id)
        if hasattr(self, "project_tree") and self.project_tree.exists(iid):
            self.project_tree.selection_set(iid)
            self.project_tree.focus(iid)
            self.project_tree.see(iid)
            self.update_project_milestones()

    def _open_task_from_global_search(self, task_id: int) -> None:
        self.notebook.select(self.tasks_tab)
        self.project_filter_var.set("Alle Projekte")
        self.status_filter_var.set("Alle Aufgaben")
        self.due_filter_var.set("Alle Fälligkeiten")
        self.energy_filter_var.set("Alle Energien")
        self.tag_filter_var.set("")
        self.context_filter_var.set("")
        self.search_var.set("")
        self.refresh_tasks()

        iid = str(task_id)
        if hasattr(self, "task_tree") and self.task_tree.exists(iid):
            self.task_tree.selection_set(iid)
            self.task_tree.focus(iid)
            self.task_tree.see(iid)
            self.update_task_details()

    def _open_template_from_global_search(self, template_id: int) -> None:
        self.notebook.select(self.templates_tab)
        self.refresh_templates()
        iid = str(template_id)
        if hasattr(self, "template_tree") and self.template_tree.exists(iid):
            self.template_tree.selection_set(iid)
            self.template_tree.focus(iid)
            self.template_tree.see(iid)
            self.update_active_template()

    def _open_milestone_from_global_search(self, project_id: int, milestone_id: int) -> None:
        self.notebook.select(self.projects_tab)
        self.refresh_projects()
        project_iid = str(project_id)
        if hasattr(self, "project_tree") and self.project_tree.exists(project_iid):
            self.project_tree.selection_set(project_iid)
            self.project_tree.focus(project_iid)
            self.project_tree.see(project_iid)
        self.update_project_milestones()
        milestone_iid = str(milestone_id)
        if hasattr(self, "milestone_tree") and self.milestone_tree.exists(milestone_iid):
            self.milestone_tree.selection_set(milestone_iid)
            self.milestone_tree.focus(milestone_iid)
            self.milestone_tree.see(milestone_iid)
            self.update_active_milestone()

    def change_selected_task_status(self, status: str) -> None:
        """Change status of currently selected task.
        
        Args:
            status: The new task status (open, in_progress, blocked, done).
        """
        task_id = self.selected_task_id()
        if task_id is None:
            return
        update_task(task_id, status=status)
        self.refresh_all()

    def add_project_dialog(self) -> None:
        """Open dialog to create a new project."""
        dialog = ProjectDialog(self, "Projekt anlegen")
        self.wait_window(dialog)
        if not dialog.result:
            return
        import traceback

        try:
            principal = current_principal()
        except Exception:
            principal = None

        print(f"DEBUG: add_project current_principal={principal}")
        print(f"DEBUG: add_project payload={dialog.result}")

        try:
            add_project(
                dialog.result["name"],
                team=dialog.result["team"],
                description=dialog.result["description"],
                status=dialog.result["status"],
                goal=dialog.result["goal"],
                milestone=dialog.result["milestone"],
                risk=dialog.result["risk"],
                risk_rows=dialog.result.get("risk_rows"),
                risk_probability=dialog.result["risk_probability"],
                risk_impact=dialog.result["risk_impact"],
                risk_weight=dialog.result["risk_weight"],
                risk_countermeasure=dialog.result["risk_countermeasure"],
                next_review_date=dialog.result["next_review_date"],
            )
        except Exception as exc:
            tb = traceback.format_exc()
            print(tb)
            messagebox.showerror("Fehler beim Anlegen", f"{type(exc).__name__}: {exc}\n\n{tb}", parent=self)
            return

        self.refresh_all()

    def edit_selected_project(self) -> None:
        """Open dialog to edit the currently selected project."""
        project_id = self.selected_project_tree_id()
        if project_id is None:
            messagebox.showinfo("Hinweis", "Bitte ein Projekt auswählen.", parent=self)
            return
        project = next((project for project in list_projects() if project["id"] == project_id), None)
        if project is None:
            return
        dialog = ProjectDialog(self, "Projekt bearbeiten", project)
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            update_project(
                project_id,
                name=dialog.result["name"],
                team=dialog.result["team"],
                description=dialog.result["description"],
                status=dialog.result["status"],
                goal=dialog.result["goal"],
                milestone=dialog.result["milestone"],
                risk=dialog.result["risk"],
                risk_rows=dialog.result.get("risk_rows"),
                risk_probability=dialog.result["risk_probability"],
                risk_impact=dialog.result["risk_impact"],
                risk_weight=dialog.result["risk_weight"],
                risk_countermeasure=dialog.result["risk_countermeasure"],
                next_review_date=dialog.result["next_review_date"],
            )
        except ValueError as exc:
            messagebox.showerror("Fehler", str(exc), parent=self)
            return
        self.refresh_all()

    def delete_selected_project(self) -> None:
        """Delete the currently selected project after confirmation."""
        project_id = self.selected_project_tree_id()
        if project_id is None:
            return
        if not messagebox.askyesno("Projekt löschen", "Projekt wirklich löschen?", parent=self):
            return
        delete_project(project_id)
        self.refresh_all()

    def add_task_dialog(self) -> None:
        """Open dialog to create a new task."""
        dialog = TaskDialog(self, "Aufgabe anlegen", list_projects())
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            add_task(
                dialog.result["title"],
                project_id=dialog.result["project_id"],
                details=dialog.result["details"],
                status=dialog.result["status"],
                priority=dialog.result["priority"],
                due_date=dialog.result["due_date"],
                blocked_reason=dialog.result["blocked_reason"],
                risk=dialog.result["risk"],
                risk_rows=dialog.result.get("risk_rows"),
                risk_probability=dialog.result["risk_probability"],
                risk_impact=dialog.result["risk_impact"],
                risk_weight=dialog.result["risk_weight"],
                risk_countermeasure=dialog.result["risk_countermeasure"],
                context=dialog.result["context"],
                energy_level=dialog.result["energy_level"],
                estimate_minutes=dialog.result["estimate_minutes"],
                tags=dialog.result["tags"],
                recurrence_days=dialog.result["recurrence_days"],
            )
        except ValueError as exc:
            messagebox.showerror("Fehler", str(exc), parent=self)
            return
        self.refresh_all()

    def edit_selected_task(self) -> None:
        """Open dialog to edit the currently selected task."""
        task_id = self.selected_task_id()
        if task_id is None:
            messagebox.showinfo("Hinweis", "Bitte eine Aufgabe auswählen.", parent=self)
            return
        task = get_task(task_id)
        if task is None:
            return
        dialog = TaskDialog(self, "Aufgabe bearbeiten", list_projects(), task)
        self.wait_window(dialog)
        if not dialog.result:
            return
        update_task(
            task_id,
            title=dialog.result["title"],
            details=dialog.result["details"],
            status=dialog.result["status"],
            priority=dialog.result["priority"],
            due_date=dialog.result["due_date"],
            blocked_reason=dialog.result["blocked_reason"],
            risk=dialog.result["risk"],
            risk_rows=dialog.result.get("risk_rows"),
            risk_probability=dialog.result["risk_probability"],
            risk_impact=dialog.result["risk_impact"],
            risk_weight=dialog.result["risk_weight"],
            risk_countermeasure=dialog.result["risk_countermeasure"],
            project_id=dialog.result["project_id"],
            context=dialog.result["context"],
            energy_level=dialog.result["energy_level"],
            estimate_minutes=dialog.result["estimate_minutes"],
            tags=dialog.result["tags"],
            recurrence_days=dialog.result["recurrence_days"],
        )
        self.refresh_all()

    def edit_task_from_board(self, status: str) -> None:
        selection = self.board_lists[status].curselection()
        if not selection:
            return
        text = self.board_lists[status].get(selection[0])
        task_id = int(text.split(":", 1)[0])
        self.task_tree.selection_set(str(task_id))
        self.edit_selected_task()

    def open_task_from_tree(self, tree: ttk.Treeview) -> None:
        selection = tree.selection()
        if not selection:
            return
        task_id = int(selection[0])
        self.task_tree.selection_set(str(task_id))
        self.notebook.select(self.tasks_tab)
        self.update_task_details()

    def complete_selected_task(self) -> None:
        """Mark the currently selected task as completed."""
        task_id = self.selected_task_id()
        if task_id is None:
            return
        complete_task(task_id)
        self.refresh_all()

    def delete_selected_task(self) -> None:
        """Delete the currently selected task after confirmation."""
        task_id = self.selected_task_id()
        if task_id is None:
            return
        if not messagebox.askyesno("Aufgabe löschen", "Aufgabe wirklich löschen?", parent=self):
            return
        delete_task(task_id)
        self.refresh_all()

    def duplicate_selected_task(self) -> None:
        """Create a copy of the currently selected task."""
        task_id = self.selected_task_id()
        if task_id is None:
            return
        task = get_task(task_id)
        if task is None:
            return
        add_task(
            f"{task['title']} (Kopie)",
            project_id=task["project_id"],
            details=task["details"],
            status="open",
            priority=task["priority"],
            due_date=task["due_date"],
            blocked_reason="",
            risk=task["risk"],
            risk_rows=self._risk_rows_from_item(dict(task)),
            risk_probability=task["risk_probability"],
            risk_impact=task["risk_impact"],
            risk_weight=task["risk_weight"],
            risk_countermeasure=task["risk_countermeasure"],
            context=task["context"],
            energy_level=task["energy_level"],
            estimate_minutes=task["estimate_minutes"],
            tags=task["tags"],
            recurrence_days=task["recurrence_days"],
        )
        self.refresh_all()

    def add_note_to_selected_task(self) -> None:
        """Add a note to the currently selected task."""
        task_id = self.selected_task_id()
        if task_id is None:
            return
        note = simpledialog.askstring("Notiz", "Notiztext:", parent=self)
        if not note:
            return
        add_task_note(task_id, note)
        self.refresh_all()

    def show_task_context_menu(self, event: tk.Event) -> None:
        row_id = self.task_tree.identify_row(event.y)
        if not row_id:
            return
        self.task_tree.selection_set(row_id)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Bearbeiten", command=self.edit_selected_task)
        menu.add_command(label="Offen", command=lambda: self.change_selected_task_status("open"))
        menu.add_command(label="In Arbeit", command=lambda: self.change_selected_task_status("in_progress"))
        menu.add_command(label="Blockiert", command=lambda: self.change_selected_task_status("blocked"))
        menu.add_command(label="Erledigt", command=self.complete_selected_task)
        menu.add_command(label="Notiz", command=self.add_note_to_selected_task)
        menu.add_command(label="Duplizieren", command=self.duplicate_selected_task)
        menu.add_command(label="Löschen", command=self.delete_selected_task)
        menu.tk_popup(event.x_root, event.y_root)

    def add_template_dialog(self) -> None:
        """Open dialog to create a new task template."""
        dialog = TemplateDialog(self, "Vorlage anlegen", list_projects())
        self.wait_window(dialog)
        if not dialog.result:
            return
        add_template(
            dialog.result["name"],
            title=dialog.result["title"],
            details=dialog.result["details"],
            project_id=dialog.result["project_id"],
            status=dialog.result["status"],
            priority=dialog.result["priority"],
            due_offset_days=dialog.result["due_offset_days"],
            context=dialog.result["context"],
            energy_level=dialog.result["energy_level"],
            tags=dialog.result["tags"],
            recurrence_days=dialog.result["recurrence_days"],
        )
        self.refresh_all()

    def edit_selected_template(self) -> None:
        """Open dialog to edit the currently selected template."""
        template_id = self.selected_template_id()
        if template_id is None:
            return
        template = next((item for item in list_templates() if item["id"] == template_id), None)
        if template is None:
            return
        dialog = TemplateDialog(self, "Vorlage bearbeiten", list_projects(), template)
        self.wait_window(dialog)
        if not dialog.result:
            return
        update_template(
            template_id,
            name=dialog.result["name"],
            title=dialog.result["title"],
            details=dialog.result["details"],
            project_id=dialog.result["project_id"],
            status=dialog.result["status"],
            priority=dialog.result["priority"],
            due_offset_days=dialog.result["due_offset_days"],
            context=dialog.result["context"],
            energy_level=dialog.result["energy_level"],
            tags=dialog.result["tags"],
            recurrence_days=dialog.result["recurrence_days"],
        )
        self.refresh_all()

    def use_selected_template(self) -> None:
        """Create a task from the currently selected template."""
        template_id = self.selected_template_id()
        if template_id is None:
            return
        title = simpledialog.askstring("Vorlage verwenden", "Optionaler neuer Titel:", parent=self)
        create_task_from_template(template_id, title=title or None)
        self.refresh_all()

    def delete_selected_template(self) -> None:
        """Delete the currently selected template after confirmation."""
        template_id = self.selected_template_id()
        if template_id is None:
            return
        if not messagebox.askyesno("Vorlage löschen", "Vorlage wirklich löschen?", parent=self):
            return
        delete_template(template_id)
        self.refresh_all()

    def export_json_dialog(self) -> None:
        """Open dialog to export data as JSON backup."""
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="project_backup.json", parent=self)
        if not path:
            return
        export_json(path)
        messagebox.showinfo("Export", f"JSON-Backup gespeichert: {path}", parent=self)

    def import_json_dialog(self) -> None:
        """Open dialog to import data from JSON backup."""
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], parent=self)
        if not path:
            return
        import_json(path, replace=True)
        self.refresh_all()
        messagebox.showinfo("Import", f"JSON importiert: {path}", parent=self)

    def export_csv_dialog(self) -> None:
        """Open dialog to export data as CSV files."""
        path = filedialog.askdirectory(parent=self)
        if not path:
            return
        export_csv(path)
        messagebox.showinfo("Export", f"CSV-Ordner gespeichert: {path}", parent=self)

    def import_csv_dialog(self) -> None:
        """Open dialog to import data from CSV files."""
        path = filedialog.askdirectory(parent=self)
        if not path:
            return
        import_csv(path, replace=True)
        self.refresh_all()
        messagebox.showinfo("Import", f"CSV importiert: {path}", parent=self)

    def add_milestone_dialog(self) -> None:
        """Open dialog to create a new project milestone."""
        project_id = self.selected_project_tree_id() or self.active_project_id
        if project_id is None:
            messagebox.showinfo("Hinweis", "Bitte ein Projekt auswählen.", parent=self)
            return
        title = simpledialog.askstring("Meilenstein", "Titel:", parent=self)
        if not title:
            return
        due_date = self._pick_date("Meilenstein", "Fällig am auswählen")
        if due_date is None:
            return
        if due_date == "":
            due_date = None
        try:
            add_milestone(project_id, title, due_date)
        except ValueError as exc:
            messagebox.showerror("Fehler", str(exc), parent=self)
            return
        self.refresh_all()

    def edit_selected_milestone(self) -> None:
        """Open dialog to edit the currently selected milestone."""
        milestone_id = self.selected_milestone_id()
        if milestone_id is None and self.active_milestone_id is not None:
            milestone_id = self.active_milestone_id
        if milestone_id is None:
            return
        project_id = self.active_project_id
        milestone = next((item for item in list_milestones(project_id) if item["id"] == milestone_id), None)
        if milestone is None:
            return
        title = simpledialog.askstring("Meilenstein", "Titel:", parent=self, initialvalue=milestone["title"])
        if not title:
            return
        due_date = self._pick_date("Meilenstein", "Fällig am auswählen", milestone["due_date"] or "")
        if due_date is None:
            return
        status_text = simpledialog.askstring(
            "Meilenstein",
            "Status (open, in_progress, blocked, done):",
            parent=self,
            initialvalue=milestone["status"],
        )
        if status_text is None:
            return
        try:
            update_milestone(milestone_id, title=title, due_date=due_date or None, status=status_text, project_id=project_id)
        except ValueError as exc:
            messagebox.showerror("Fehler", str(exc), parent=self)
            return
        self.refresh_all()

    def _pick_date(self, title: str, prompt: str, initial_value: str = "") -> str | None:
        try:
            initial_date = date.fromisoformat(initial_value) if initial_value else date.today()
        except ValueError:
            initial_date = date.today()
        dialog = DatePickerDialog(self, title, initial_date=initial_date)
        self.wait_window(dialog)
        return dialog.result

    def delete_selected_milestone(self) -> None:
        """Delete the currently selected milestone after confirmation."""
        milestone_id = self.selected_milestone_id() or self.active_milestone_id
        if milestone_id is None:
            return
        if not messagebox.askyesno("Meilenstein löschen", "Meilenstein wirklich löschen?", parent=self):
            return
        delete_milestone(milestone_id)
        self.refresh_all()

    def update_task_details_from_selection(self) -> None:
        """Update task details panel based on current selection."""
        self.update_task_details()

    def fill_weekly_report_today(self) -> None:
        """Fill the weekly report date field with today's date."""
        self.report_date_var.set(date.today().isoformat())
        self.update_weekly_report_milestone(silent=True)

    def _selected_report_project_id(self) -> int | None:
        return id_from_labeled_value(self.report_project_var.get(), "Projekt wählen")

    def _selected_report_project(self) -> dict[str, object] | None:
        project_id = self._selected_report_project_id()
        if project_id is None:
            return None
        project = next((item for item in list_projects() if item["id"] == project_id), None)
        return dict(project) if project is not None else None

    def _selected_report_date(self) -> date:
        date_text = self.report_date_var.get().strip()
        if not date_text:
            return date.today()
        try:
            return date.fromisoformat(date_text)
        except ValueError:
            return date.today()

    def _pick_weekly_report_milestone(self) -> tuple[str, str] | None:
        project_id = self._selected_report_project_id()
        if project_id is None:
            return None

        milestones = [dict(item) for item in list_milestones(project_id)]
        if not milestones:
            return None

        selected_date = self._selected_report_date().isoformat()
        dated = [m for m in milestones if m.get("due_date")]

        future_open = [m for m in dated if str(m.get("due_date", "")) >= selected_date and m.get("status") != "done"]
        future_any = [m for m in dated if str(m.get("due_date", "")) >= selected_date]
        overdue_open = [m for m in dated if str(m.get("due_date", "")) < selected_date and m.get("status") != "done"]
        undated_open = [m for m in milestones if not m.get("due_date") and m.get("status") != "done"]

        chosen: dict[str, object] | None = None
        if future_open:
            chosen = sorted(future_open, key=lambda m: str(m.get("due_date", "")))[0]
        elif future_any:
            chosen = sorted(future_any, key=lambda m: str(m.get("due_date", "")))[0]
        elif overdue_open:
            chosen = sorted(overdue_open, key=lambda m: str(m.get("due_date", "")), reverse=True)[0]
        elif undated_open:
            chosen = undated_open[0]
        elif milestones:
            chosen = milestones[0]

        if chosen is None:
            return None

        title = str(chosen.get("title", "")).strip()
        due_date = str(chosen.get("due_date", "") or "").strip()
        if not title:
            return None
        return title, due_date

    def update_weekly_report_milestone(self, silent: bool = False) -> None:
        picked = self._pick_weekly_report_milestone()
        if picked is None:
            self.report_milestone_var.set("")
            self.report_milestone_date_var.set("")
            if not silent:
                self.report_status_message_var.set("Kein Meilenstein für das gewählte Projekt vorhanden.")
            return

        milestone_title, milestone_date = picked
        self.report_milestone_var.set(milestone_title)
        self.report_milestone_date_var.set(milestone_date)
        if not silent:
            self.report_status_message_var.set("Meilenstein wurde automatisch aus Projekt und Datum gesetzt.")

    def _dynamic_report_var_list(self, section: str) -> list[tk.StringVar]:
        mapping = {
            "planned": self.report_plan_vars,
            "achieved": self.report_goal_vars,
            "not_achieved": self.report_not_achieved_vars,
        }
        return mapping[section]

    def _new_dynamic_report_var(self, value: str = "") -> tk.StringVar:
        var = tk.StringVar(value=value)
        var.trace_add("write", lambda *_: self._on_dynamic_report_items_changed())
        return var

    def _init_dynamic_report_items(self) -> None:
        self.report_plan_vars = [self._new_dynamic_report_var()]
        self.report_goal_vars = [self._new_dynamic_report_var()]
        self.report_not_achieved_vars = [self._new_dynamic_report_var()]

    def _normalize_dynamic_report_section(self, section: str) -> bool:
        values = self._dynamic_report_var_list(section)
        changed = False
        while len(values) > 1 and not values[-1].get().strip() and not values[-2].get().strip():
            values.pop()
            changed = True
        if not values:
            values.append(self._new_dynamic_report_var())
            changed = True
        elif values[-1].get().strip():
            values.append(self._new_dynamic_report_var())
            changed = True
        return changed

    def _render_dynamic_report_section(self, section: str) -> None:
        frame = getattr(self, f"report_{section}_items_frame", None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()

        values = self._dynamic_report_var_list(section)
        for idx, var in enumerate(values):
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=(0 if idx == 0 else 4, 0))
            ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            is_placeholder = idx == len(values) - 1 and not var.get().strip()
            ttk.Button(
                row,
                text="Entfernen",
                width=10,
                state="disabled" if is_placeholder else "normal",
                command=lambda i=idx, s=section: self.remove_dynamic_report_item(s, i),
            ).pack(side="left", padx=(8, 0))

    def render_all_dynamic_report_sections(self) -> None:
        self._render_dynamic_report_section("planned")
        self._render_dynamic_report_section("achieved")
        self._render_dynamic_report_section("not_achieved")

    def _dynamic_report_items(self, section: str) -> list[str]:
        values = []
        for var in self._dynamic_report_var_list(section):
            text = var.get().strip()
            if text:
                values.append(text)
        return values

    def _set_dynamic_report_items(self, section: str, items: list[str]) -> None:
        values = self._dynamic_report_var_list(section)
        values.clear()
        for item in items:
            text = item.strip()
            if text:
                values.append(self._new_dynamic_report_var(text))
        values.append(self._new_dynamic_report_var())
        self._render_dynamic_report_section(section)

    def _append_dynamic_report_items(self, section: str, items: list[str]) -> None:
        existing = self._dynamic_report_items(section)
        merged = list(existing)
        for item in items:
            text = item.strip()
            if text and text not in merged:
                merged.append(text)
        self._set_dynamic_report_items(section, merged)

    def remove_dynamic_report_item(self, section: str, index: int) -> None:
        values = self._dynamic_report_var_list(section)
        if index < 0 or index >= len(values):
            return
        if len(values) == 1:
            values[0].set("")
        else:
            values.pop(index)
        self._normalize_dynamic_report_section(section)
        self._render_dynamic_report_section(section)
        self.preview_weekly_report(silent=True)

    def _on_dynamic_report_items_changed(self) -> None:
        changed = False
        changed = self._normalize_dynamic_report_section("planned") or changed
        changed = self._normalize_dynamic_report_section("achieved") or changed
        changed = self._normalize_dynamic_report_section("not_achieved") or changed
        if changed:
            self.render_all_dynamic_report_sections()
        self.preview_weekly_report(silent=True)

    @staticmethod
    def _task_status(task: dict[str, object]) -> str:
        return str(task.get("status", "open"))

    @staticmethod
    def _task_text(task: dict[str, object], include_remaining: bool) -> str:
        title = str(task.get("title", "")).strip()
        estimate = task.get("estimate_minutes")
        if include_remaining and isinstance(estimate, int) and estimate > 0:
            return f"{title} (Rest: {estimate} min)"
        return title

    @staticmethod
    def _risk_level_text(weight_value: object) -> str:
        try:
            weight = int(weight_value)
        except (TypeError, ValueError):
            weight = 3
        weight = max(1, min(5, weight))
        labels = {1: "sehr gering", 2: "gering", 3: "mittel", 4: "hoch", 5: "sehr hoch"}
        return f"{weight}/5 ({labels[weight]})"

    @staticmethod
    def _risk_text(task_or_project: dict[str, object], key: str) -> str:
        return str(task_or_project.get(key, "")).strip()

    @staticmethod
    def _risk_rows_from_item(item: dict[str, object]) -> list[dict[str, object]]:
        raw_json = str(item.get("risk_rows_json", "") or "")
        if not raw_json:
            return []
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []

        rows: list[dict[str, object]] = []
        for row in parsed:
            if not isinstance(row, dict):
                continue
            risk_text = str(row.get("risk", "")).strip()
            if not risk_text:
                continue
            try:
                probability = int(row.get("probability", item.get("risk_probability", item.get("risk_weight", 3))))
            except (TypeError, ValueError):
                probability = 3
            try:
                impact = int(row.get("impact", item.get("risk_impact", item.get("risk_weight", 3))))
            except (TypeError, ValueError):
                impact = 3
            rows.append(
                {
                    "risk": risk_text,
                    "countermeasure": str(row.get("countermeasure", "")).strip(),
                    "probability": max(1, min(5, probability)),
                    "impact": max(1, min(5, impact)),
                }
            )
        return rows

    @staticmethod
    def _split_risk_lines(value: object) -> list[str]:
        return [line.strip() for line in str(value or "").splitlines() if line.strip()]

    def _risk_probability_text(self, item: dict[str, object]) -> str:
        return self._risk_level_text(item.get("risk_probability", item.get("risk_weight", 3)))

    def _risk_impact_text(self, item: dict[str, object]) -> str:
        return self._risk_level_text(item.get("risk_impact", item.get("risk_weight", 3)))

    def _project_risk_rows(self) -> list[dict[str, str]]:
        project = self._selected_report_project()
        if project is None:
            return []
        structured_rows = self._risk_rows_from_item(project)
        if structured_rows:
            return [
                {
                    "risk": str(row["risk"]),
                    "probability": self._risk_level_text(row.get("probability", 3)),
                    "impact": self._risk_level_text(row.get("impact", 3)),
                    "countermeasure": str(row.get("countermeasure", "")).strip() or "-",
                }
                for row in structured_rows
            ]
        risks = self._split_risk_lines(project.get("risk", ""))
        if not risks:
            return []
        countermeasures = self._split_risk_lines(project.get("risk_countermeasure", ""))
        probability_text = self._risk_probability_text(project)
        impact_text = self._risk_impact_text(project)
        rows: list[dict[str, str]] = []
        for idx, risk in enumerate(risks):
            countermeasure = countermeasures[idx] if idx < len(countermeasures) else ""
            rows.append(
                {
                    "risk": risk,
                    "probability": probability_text,
                    "impact": impact_text,
                    "countermeasure": countermeasure or "-",
                }
            )
        return rows

    def _task_risk_rows(self) -> list[dict[str, str]]:
        tasks = self._selected_report_tasks()
        if not tasks:
            tasks = list(self.report_project_tasks_cache)

        rows: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for task in tasks:
            structured_rows = self._risk_rows_from_item(task)
            if structured_rows:
                title = str(task.get("title", "")).strip()
                for row in structured_rows:
                    risk = f"{title}: {row['risk']}" if title else row["risk"]
                    probability_text = self._risk_level_text(row.get("probability", 3))
                    impact_text = self._risk_level_text(row.get("impact", 3))
                    countermeasure_text = str(row.get("countermeasure", "")).strip() or "-"
                    key = (str(risk), probability_text, impact_text, countermeasure_text)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        {
                            "risk": str(risk),
                            "probability": probability_text,
                            "impact": impact_text,
                            "countermeasure": countermeasure_text,
                        }
                    )
                continue
            risk_items = self._split_risk_lines(task.get("risk", ""))
            if not risk_items:
                continue
            countermeasures = self._split_risk_lines(task.get("risk_countermeasure", ""))
            title = str(task.get("title", "")).strip()
            probability_text = self._risk_probability_text(task)
            impact_text = self._risk_impact_text(task)
            for idx, risk_text in enumerate(risk_items):
                risk = f"{title}: {risk_text}" if title else risk_text
                countermeasure = countermeasures[idx] if idx < len(countermeasures) else ""
                key = (risk, probability_text, impact_text, countermeasure or "-")
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "risk": risk,
                        "probability": probability_text,
                        "impact": impact_text,
                        "countermeasure": countermeasure or "-",
                    }
                )
        return rows

    def _select_report_tasks_by_predicate(self, predicate) -> None:
        if not hasattr(self, "report_tasks_listbox"):
            return
        self.report_tasks_listbox.selection_clear(0, tk.END)
        for idx, task in enumerate(self.report_project_tasks_cache):
            if predicate(task):
                self.report_tasks_listbox.selection_set(idx)

    def select_all_report_tasks(self) -> None:
        """Select all tasks in the report task list."""
        self._select_report_tasks_by_predicate(lambda _: True)

    def invert_report_task_selection(self) -> None:
        """Invert the selection of tasks in the report task list."""
        if not hasattr(self, "report_tasks_listbox"):
            return
        selected = set(self.report_tasks_listbox.curselection())
        self.report_tasks_listbox.selection_clear(0, tk.END)
        for idx in range(self.report_tasks_listbox.size()):
            if idx not in selected:
                self.report_tasks_listbox.selection_set(idx)

    def select_done_report_tasks(self) -> None:
        """Select all completed tasks in the report task list."""
        self._select_report_tasks_by_predicate(lambda task: self._task_status(task) == "done")

    def select_open_report_tasks(self) -> None:
        """Select all open (incomplete) tasks in the report task list."""
        self._select_report_tasks_by_predicate(lambda task: self._task_status(task) != "done")

    def load_report_project_tasks(self, silent: bool = False) -> None:
        """Load tasks for the selected project into the report task list.
        
        Args:
            silent: If True, suppress status messages.
        """
        if not hasattr(self, "report_tasks_listbox"):
            return
        project_id = self._selected_report_project_id()
        self.report_tasks_listbox.delete(0, tk.END)
        self.report_project_tasks_cache = []
        if project_id is None:
            if not silent:
                self.report_status_message_var.set("Bitte ein Projekt auswählen.")
            return

        self.report_project_tasks_cache = [dict(row) for row in list_tasks(project_id=project_id, include_done=True)]
        for task in self.report_project_tasks_cache:
            status = str(task.get("status", "open"))
            estimate = task.get("estimate_minutes")
            estimate_text = f" | {estimate} min" if isinstance(estimate, int) and estimate > 0 else ""
            self.report_tasks_listbox.insert(tk.END, f"[{status}] {task.get('title', '')}{estimate_text}")

        self.update_weekly_report_milestone(silent=True)

        if not silent:
            self.report_status_message_var.set(f"{len(self.report_project_tasks_cache)} Aufgaben geladen. Meilenstein automatisch aktualisiert.")

    def _selected_report_tasks(self) -> list[dict[str, object]]:
        if not hasattr(self, "report_tasks_listbox"):
            return []
        selected_indices = self.report_tasks_listbox.curselection()
        return [self.report_project_tasks_cache[i] for i in selected_indices if i < len(self.report_project_tasks_cache)]

    def autofill_report_from_project_tasks(self) -> None:
        """Automatically fill report sections with selected project tasks."""
        project_id = self._selected_report_project_id()
        if project_id is None:
            self.report_status_message_var.set("Bitte zuerst ein Projekt auswählen.")
            return

        if not self.report_project_tasks_cache:
            self.load_report_project_tasks(silent=True)

        tasks = self._selected_report_tasks()
        if not tasks:
            self.report_status_message_var.set("Bitte Aufgaben in der Liste auswählen.")
            return

        done_tasks = [task for task in tasks if self._task_status(task) == "done"]
        open_tasks = [task for task in tasks if self._task_status(task) != "done"]

        # Planned contains all selected tasks, including already completed ones.
        planned = [self._task_text(task, include_remaining=False) for task in tasks]
        achieved = [self._task_text(task, include_remaining=False) for task in done_tasks]
        not_achieved = [self._task_text(task, include_remaining=True) for task in open_tasks]

        self._append_dynamic_report_items("planned", planned)
        self._append_dynamic_report_items("achieved", achieved)
        self._append_dynamic_report_items("not_achieved", not_achieved)

        if done_tasks and not open_tasks and not self.report_status_var.get().strip():
            self.report_status_var.set("Schneller als geplant")
        elif open_tasks and not self.report_status_var.get().strip():
            self.report_status_var.set("Im Plan")

        self.preview_weekly_report()
        self.report_status_message_var.set("Ausgewählte Aufgaben wurden hinzugefügt; Projekt- und Aufgabenrisiken wurden übernommen.")

    def _weekly_report_vars(self) -> list[tk.StringVar]:
        return [
            self.report_date_var,
            self.report_status_var,
            self.report_delay1_var,
            self.report_delay2_var,
            self.report_milestone_var,
            self.report_milestone_date_var,
        ]

    def _weekly_report_kwargs(self) -> dict[str, object]:
        project = self._selected_report_project() or {}
        return {
            "project_title": str(project.get("name", "")).strip() or None,
            "project_team": str(project.get("team", "")).strip() or None,
            "date_value": self.report_date_var.get().strip() or None,
            "planned_items": self._dynamic_report_items("planned"),
            "achieved_items": self._dynamic_report_items("achieved"),
            "not_achieved_items": self._dynamic_report_items("not_achieved"),
            "status_text": self.report_status_var.get().strip() or None,
            "delay_measures": [self.report_delay1_var.get(), self.report_delay2_var.get()],
            "project_risks": self._project_risk_rows(),
            "task_risks": self._task_risk_rows(),
            "next_milestone": self.report_milestone_var.get().strip() or None,
            "next_milestone_date": self.report_milestone_date_var.get().strip() or None,
        }

    def _init_weekly_report_traces(self) -> None:
        for var in self._weekly_report_vars():
            var.trace_add("write", lambda *_: self.preview_weekly_report(silent=True))
        self.report_date_var.trace_add("write", lambda *_: self.update_weekly_report_milestone(silent=True))

    def clear_weekly_report_form(self) -> None:
        """Clear all fields and reset the weekly report form to defaults."""
        for var in self._weekly_report_vars():
            var.set("")
        self._set_dynamic_report_items("planned", [])
        self._set_dynamic_report_items("achieved", [])
        self._set_dynamic_report_items("not_achieved", [])
        self.report_status_message_var.set("Formular zurückgesetzt")
        self.fill_weekly_report_today()
        self.preview_weekly_report()

    def _weekly_report_markdown(self) -> str:
        return build_weekly_project_report_markdown(**self._weekly_report_kwargs())

    def preview_weekly_report(self, silent: bool = False) -> None:
        """Update and display the weekly report preview.
        
        Args:
            silent: If True, suppress status messages.
        """
        if not hasattr(self, "report_preview_text"):
            return
        report_md = self._weekly_report_markdown()
        self.report_preview_text.configure(state="normal")
        self.report_preview_text.delete("1.0", tk.END)
        self.report_preview_text.insert("1.0", report_md)
        self.report_preview_text.configure(state="disabled")
        if not silent:
            self.report_status_message_var.set("Vorschau aktualisiert")

    def save_weekly_report(self) -> None:
        """Save the weekly report to a markdown file."""
        suggested_name = f"wochenbericht_{self.report_date_var.get().strip().replace('-', '') or 'template'}.md"
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown", "*.md")],
            initialfile=suggested_name,
            parent=self,
        )
        if not path:
            return
        output_file = generate_weekly_project_report(output_path=path, **self._weekly_report_kwargs())
        self.preview_weekly_report()
        self.report_status_message_var.set(f"Bericht gespeichert: {output_file}")
        messagebox.showinfo("Wochenbericht", f"Markdown gespeichert:\n{output_file}", parent=self)


def launch_gui(user_data: dict[str, object] | None = None) -> int:
    app = ProjectManagerApp(user_data=user_data)
    app.mainloop()
    return 0
