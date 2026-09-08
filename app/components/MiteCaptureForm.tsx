'use client';
import { PestCaptureForm } from './PestCaptureForm';
export function MiteCaptureForm(props: Parameters<typeof PestCaptureForm>[0]) { return <PestCaptureForm {...props} defaultPestCode="MITE" />; }
