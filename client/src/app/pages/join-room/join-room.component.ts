import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';

@Component({
  standalone: true,
  selector: 'app-join-room',
  imports: [CommonModule],
  template: `
    <div class="page-wrapper">
      <h2>Join a Room</h2>
      <p>This is a placeholder for the Join Room flow.</p>
      <button (click)="goHome()">Back</button>
    </div>
  `
})
export class JoinRoomComponent {
  constructor(private router: Router) {}
  goHome() { this.router.navigate(['']); }
}
