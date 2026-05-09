import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';

@Component({
  standalone: true,
  selector: 'app-create-room',
  imports: [CommonModule],
  template: `
    <div class="page-wrapper">
      <h2>Create a Room</h2>
      <p>This is a placeholder for the Create Room flow.</p>
      <button (click)="goHome()">Back</button>
    </div>
  `
})
export class CreateRoomComponent {
  constructor(private router: Router) {}
  goHome() { this.router.navigate(['']); }
}
