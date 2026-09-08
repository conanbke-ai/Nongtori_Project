CREATE TABLE `crop_profiles` (
	`crop_code` text PRIMARY KEY NOT NULL,
	`image_uri` text,
	`description_ko` text DEFAULT '' NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`crop_code`) REFERENCES `crop_types`(`code`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE TABLE `crop_guides` (
	`id` text PRIMARY KEY NOT NULL,
	`crop_code` text NOT NULL,
	`cultivar_code` text,
	`guide_type` text NOT NULL,
	`title` text NOT NULL,
	`symptom_summary` text NOT NULL,
	`risk_summary` text NOT NULL,
	`prevention_summary` text NOT NULL,
	`response_summary` text NOT NULL,
	`source_title` text NOT NULL,
	`source_url` text NOT NULL,
	`reviewed_at` text NOT NULL,
	`display_order` integer DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'ACTIVE' NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`crop_code`) REFERENCES `crop_types`(`code`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`cultivar_code`) REFERENCES `cultivars`(`code`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `idx_crop_guides_crop_cultivar` ON `crop_guides` (`crop_code`,`cultivar_code`,`status`,`display_order`);
--> statement-breakpoint
INSERT OR IGNORE INTO `crop_types` (`code`,`display_name_ko`,`created_at`) VALUES
('STRAWBERRY','딸기','2026-08-27T00:00:00.000Z');
--> statement-breakpoint
INSERT OR IGNORE INTO `crop_profiles` (`crop_code`,`image_uri`,`description_ko`,`updated_at`) VALUES
('STRAWBERRY','/crops/strawberry-cover-v1.png','수확 과실 품질 판독과 병해충 조기예찰을 함께 관리합니다.','2026-08-27T00:00:00.000Z');
--> statement-breakpoint
INSERT OR IGNORE INTO `crop_guides` (`id`,`crop_code`,`cultivar_code`,`guide_type`,`title`,`symptom_summary`,`risk_summary`,`prevention_summary`,`response_summary`,`source_title`,`source_url`,`reviewed_at`,`display_order`,`status`,`created_at`,`updated_at`) VALUES
('guide-strawberry-mite','STRAWBERRY',NULL,'PEST','점박이응애','잎 뒷면에서 흡즙하며 초기에는 잎 표면에 작은 황백색 반점이 나타나고 밀도가 높아지면 잎이 마르거나 거미줄이 보일 수 있습니다.','고온·건조 조건에서 세대가 빨라질 수 있어 하우스 가장자리와 잎 뒷면을 먼저 확인하는 것이 중요합니다.','새 묘와 반입 자재를 점검하고 구역별로 잎 뒷면을 정기 관찰하며 잡초와 심한 피해 잎을 관리합니다.','의심 구역을 표시하고 잎 뒷면을 확대 관찰해 재확인합니다. 방제 시 등록 약제와 안전사용기준을 확인하고 저항성 관리를 고려합니다.','국가농작물병해충관리시스템','https://ncpms.rda.go.kr/npms/HlsctIstguInfoDtlR.np?hlsctIstguNo=H00000527&totalSearchYn=Y','2026-08-27',10,'ACTIVE','2026-08-27T00:00:00.000Z','2026-08-27T00:00:00.000Z'),
('guide-strawberry-powdery','STRAWBERRY',NULL,'DISEASE','흰가루병','잎 뒷면에 흰색 균총이 나타나며 과실에는 흰가루를 뿌린 듯한 증상이 생길 수 있습니다. 어린 과실은 비대가 억제될 수 있습니다.','주로 봄과 가을의 시설재배에서 발생하며 병든 식물체 잔재가 전염원이 될 수 있습니다.','건전한 묘를 사용하고 통풍·환기·관수를 관리하며 발생 잎이나 발병 과실은 바로 제거합니다.','증상 부위를 격리·제거하고 확산 범위를 확인합니다. 등록 약제를 사용할 때는 딸기 적용 여부와 수확 전 안전사용기준을 확인합니다.','국가농작물병해충관리시스템','https://ncpms.rda.go.kr/npms/SicknsInfoDtlR.np?sicknsListNo=D00000459&totalSearchYn=Y','2026-08-27',20,'ACTIVE','2026-08-27T00:00:00.000Z','2026-08-27T00:00:00.000Z'),
('guide-strawberry-gray-mold','STRAWBERRY',NULL,'DISEASE','잿빛곰팡이병','과실·꽃받침·과경·잎·엽병 등 지상부에 발생하며 특히 과실에 큰 피해를 줄 수 있습니다.','저온·다습하고 밤낮 온도차가 큰 시설 환경에서 발생 위험이 높아집니다.','시설 내 과습을 줄이고 환기와 보온을 함께 관리하며 병든 과실과 잔여물은 즉시 제거합니다.','발병 과실과 주변 잔재를 분리하고 인접 주를 점검합니다. 등록 약제와 안전사용기준은 공식 시스템에서 최종 확인합니다.','농촌진흥청 농사로','https://www.nongsaro.go.kr/portal/ps/psb/psby/vodPlay.ps?menuId=PS00069&mvpClipNo=3&mvpNo=743','2026-08-27',30,'ACTIVE','2026-08-27T00:00:00.000Z','2026-08-27T00:00:00.000Z');
