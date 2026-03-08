"use client";

import React, { useState } from 'react';
import styles from '../home.module.css'; // Corrected path to import styles

const mockBlastRadiusData = {
  impactedUsers: 12345,
  revenueRiskUSD: 56789,
  slaBreachRiskPercent: 45,
};

const BlastRadiusPreview = ({ initiallyOpen = false }) => {
  const [isOpen, setIsOpen] = useState(initiallyOpen);

  const toggleOpen = () => setIsOpen(!isOpen);

  return (
    <details
      className={styles.foldPanel}
      open={isOpen}
      style={{ '--panel-color': '#1e3a8a', '--pill-color': '#2563eb' }} // Example styling
    >
      <summary className={styles.foldSummary} onClick={toggleOpen}>
        <span>Blast Radius Preview</span>
        <span className={styles.foldPill}>{isOpen ? 'Hide' : 'Show'}</span>
      </summary>
      <div className={styles.foldBody}>
        <div className={styles.foldRow}>
          <span>Estimated impacted users</span>
          <strong>{mockBlastRadiusData.impactedUsers.toLocaleString()}</strong>
        </div>
        <div className={styles.foldRow}>
          <span>Revenue risk (USD/hr)</span>
          <strong>${mockBlastRadiusData.revenueRiskUSD.toLocaleString()}</strong>
        </div>
        <div className={styles.foldRow}>
          <span>SLA breach risk</span>
          <strong style={{ color: mockBlastRadiusData.slaBreachRiskPercent > 50 ? "#fca5a5" : "#fde68a" }}>
            {mockBlastRadiusData.slaBreachRiskPercent}%
          </strong>
        </div>
      </div>
    </details>
  );
};

export default BlastRadiusPreview;
