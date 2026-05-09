import { Routes } from '@angular/router';
import { HomeComponent } from './pages/app/app.component';
import { CreateRoomComponent } from './pages/create-room/create-room.component';
import { JoinRoomComponent } from './pages/join-room/join-room.component';
import { RoomComponent } from './pages/room/room.component';

export const routes: Routes = [
	{ path: '', component: HomeComponent },
	{ path: 'create-room', component: CreateRoomComponent },
	{ path: 'join-room', component: JoinRoomComponent },
	{ path: 'room', component: RoomComponent },
	{ path: '**', redirectTo: '' }
];
