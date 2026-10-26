import { Component, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../auth';

@Component({
  selector: 'view-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class LoginView {
  protected readonly auth = inject(AuthService);

  protected readonly token = signal('');
  protected readonly busy = signal(false);
  protected readonly error = signal('');

  submit() {
    const t = this.token().trim();
    if (!t) {
      this.error.set('Bitte Token eingeben.');
      return;
    }
    this.busy.set(true);
    this.error.set('');
    this.auth.setToken(t);
    this.auth.verify().subscribe((ok) => {
      this.busy.set(false);
      if (!ok) {
        this.auth.setToken(null);
        this.error.set('Token nicht akzeptiert.');
      }
    });
  }
}
